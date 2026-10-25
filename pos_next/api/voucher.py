# -*- coding: utf-8 -*-
# Copyright (c) 2026, POS Next and contributors
# For license information, please see license.txt

"""Prepaid Voucher system.

A customer buys a voucher book (an Item flagged `mu_is_voucher_item` carrying
`mu_voucher_units`). Buying it is an ordinary taxed POS sale — VAT is collected
here. Each unit later entitles the customer to one physical hand-over (e.g. a
gas-cylinder swap). Redemption is NOT a taxable supply (single-purpose voucher),
so it issues NO tax invoice: it only decrements the balance and issues the
physical item via a Stock Entry (Material Issue).
"""

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from pos_next.api.security import require_pos_profile_access, require_shift_access
from pos_next.api.whatsapp_hook import notify_customer


# ---------------------------------------------------------------------------
# Balance helpers
# ---------------------------------------------------------------------------

def _lock_voucher_balance(balance_name):
	"""Serialize redemption against this balance record inside the current DB transaction."""
	if not balance_name:
		return
	table = '"tabPrepaid Voucher Balance"' if getattr(frappe.db, "db_type", None) == "postgres" else "`tabPrepaid Voucher Balance`"
	frappe.db.sql(f"SELECT name FROM {table} WHERE name = %s FOR UPDATE", (balance_name,))


def _get_or_create_balance(customer, company=None, branch=None):
	if branch:
		name = frappe.db.get_value("Prepaid Voucher Balance", {"customer": customer, "branch": branch})
	else:
		name = frappe.db.get_value("Prepaid Voucher Balance", {"customer": customer, "is_general": 1})
		if not name:
			name = frappe.db.get_value("Prepaid Voucher Balance", {"customer": customer, "branch": ("in", ["", None])})
		if not name and frappe.db.exists("Prepaid Voucher Balance", customer):
			name = customer

	if name:
		return frappe.get_doc("Prepaid Voucher Balance", name)

	doc = frappe.new_doc("Prepaid Voucher Balance")
	doc.customer = customer
	doc.branch = branch or None
	doc.is_general = 0 if branch else 1
	doc.company = company
	doc.total_purchased = 0
	doc.total_redeemed = 0
	doc.insert(ignore_permissions=True)
	return doc


def get_balance_value(customer, branch=None):
	"""Current remaining units for a customer and optional branch.
	If branch provided: returns sum of branch balance + general balance.
	If no branch: returns general balance (or all balances if no branch distinction).
	"""
	if not customer:
		return 0

	try:
		if branch:
			gen = frappe.db.sql("""
				select coalesce(sum(current_balance), 0)
				from `tabPrepaid Voucher Balance`
				where customer = %s and (is_general = 1 or branch is null or branch = '')
			""", customer)
			gen_val = cint(gen[0][0]) if gen else 0

			br = frappe.db.sql("""
				select coalesce(sum(current_balance), 0)
				from `tabPrepaid Voucher Balance`
				where customer = %s and branch = %s
			""", (customer, branch))
			br_val = cint(br[0][0]) if br else 0

			return gen_val + br_val
		else:
			all_bal = frappe.db.sql("""
				select coalesce(sum(current_balance), 0)
				from `tabPrepaid Voucher Balance`
				where customer = %s
			""", customer)
			return cint(all_bal[0][0]) if all_bal else 0
	except Exception:
		val = frappe.db.get_value("Prepaid Voucher Balance", {"customer": customer}, "current_balance")
		return cint(val)


@frappe.whitelist()
def get_voucher_balance(customer, pos_profile=None, branch=None):
	"""Public: current balance + breakdown + whether the voucher system is enabled."""
	enabled = 0
	if pos_profile:
		require_pos_profile_access(pos_profile)
		enabled = cint(frappe.db.get_value("POS Profile", pos_profile, "mu_voucher_enabled"))

	general_bal = 0
	branch_bal = 0
	has_branch_vouchers = False
	branch_balance_map = {}

	if customer:
		try:
			gen = frappe.db.sql("""
				select coalesce(sum(current_balance), 0)
				from `tabPrepaid Voucher Balance`
				where customer = %s and (is_general = 1 or branch is null or branch = '')
			""", customer)
			general_bal = cint(gen[0][0]) if gen else 0

			# Check all active branch-dedicated balances for this customer
			branch_rows = frappe.db.sql("""
				select branch, current_balance
				from `tabPrepaid Voucher Balance`
				where customer = %s and branch is not null and branch != '' and current_balance > 0
			""", customer, as_dict=True)
			if branch_rows:
				has_branch_vouchers = True
				for r in branch_rows:
					branch_balance_map[r.branch] = cint(r.current_balance)

			if branch:
				branch_bal = branch_balance_map.get(branch, 0)
				if not branch_bal:
					br = frappe.db.sql("""
						select coalesce(sum(current_balance), 0)
						from `tabPrepaid Voucher Balance`
						where customer = %s and branch = %s
					""", (customer, branch))
					branch_bal = cint(br[0][0]) if br else 0
		except Exception:
			general_bal = cint(frappe.db.get_value("Prepaid Voucher Balance", {"customer": customer}, "current_balance"))

	total_all = general_bal + sum(branch_balance_map.values())
	total = (general_bal + branch_bal) if branch else total_all
	return {
		"customer": customer,
		"branch": branch,
		"balance": total,
		"general_balance": general_bal,
		"branch_balance": branch_bal,
		"has_branch_vouchers": has_branch_vouchers,
		"branch_balance_map": branch_balance_map,
		"enabled": enabled,
	}


def _record_transaction(customer, qty, txn_type, balance_after, company=None,
	pos_profile=None, pos_opening_shift=None, reference_doctype=None,
	reference_name=None, stock_entry=None, branch=None, remarks=None):
	txn = frappe.new_doc("Prepaid Voucher Transaction")
	txn.customer = customer
	try:
		txn.branch = branch
	except Exception:
		pass
	txn.transaction_type = txn_type
	txn.quantity = qty
	txn.balance_after = balance_after
	txn.company = company
	txn.pos_profile = pos_profile
	txn.pos_opening_shift = pos_opening_shift
	txn.posting_datetime = now_datetime()
	txn.cashier = frappe.session.user
	txn.reference_doctype = reference_doctype
	txn.reference_name = reference_name
	txn.stock_entry = stock_entry
	txn.remarks = remarks
	txn.insert(ignore_permissions=True)
	return txn


# ---------------------------------------------------------------------------
# Purchase side — hooked on Sales Invoice submit / cancel
# ---------------------------------------------------------------------------

def _voucher_units_in_invoice(doc):
	"""Sum voucher units sold in this invoice: qty * Item.mu_voucher_units."""
	total = 0
	for row in doc.get("items", []):
		flag, units = frappe.db.get_value(
			"Item", row.item_code, ["mu_is_voucher_item", "mu_voucher_units"]
		) or (0, 0)
		if cint(flag) and cint(units):
			total += cint(units) * cint(row.qty)
	return total


def on_sales_invoice_submit(doc, method=None):
	"""Credit the customer's voucher balance when a voucher book is sold."""
	if not doc.get("customer"):
		return
	units = _voucher_units_in_invoice(doc)
	if units <= 0:
		return

	# Determine branch allocation
	branch = None
	if doc.get("mu_voucher_branch_only") and doc.get("customer_address"):
		branch = doc.get("customer_address")

	bal = _get_or_create_balance(doc.customer, doc.company, branch=branch)
	bal.total_purchased = cint(bal.total_purchased) + units
	bal.low_balance_notified = 0  # topped up -> allow future low-balance alert
	bal.save(ignore_permissions=True)
	_record_transaction(
		doc.customer, units, "Purchase", cint(bal.current_balance),
		company=doc.company, pos_profile=doc.get("pos_profile"),
		reference_doctype="Sales Invoice", reference_name=doc.name,
		branch=branch,
		remarks=_("Voucher book purchase - {0}").format(
			_("Dedicated to branch: {0}").format(branch) if branch else _("General")
		),
	)


def on_sales_invoice_cancel(doc, method=None):
	"""Reverse the credited units if a voucher-book invoice is cancelled."""
	if not doc.get("customer"):
		return
	units = _voucher_units_in_invoice(doc)
	if units <= 0:
		return

	branch = None
	if doc.get("mu_voucher_branch_only") and doc.get("customer_address"):
		branch = doc.get("customer_address")

	bal = _get_or_create_balance(doc.customer, doc.company, branch=branch)
	bal.total_purchased = max(0, cint(bal.total_purchased) - units)
	bal.save(ignore_permissions=True)
	_record_transaction(
		doc.customer, -units, "Purchase", cint(bal.current_balance),
		company=doc.company, pos_profile=doc.get("pos_profile"),
		reference_doctype="Sales Invoice", reference_name=doc.name,
		branch=branch,
		remarks=_("Reversal of cancelled voucher-book invoice"),
	)


# ---------------------------------------------------------------------------
# Redemption side — POS action (no tax invoice)
# ---------------------------------------------------------------------------

def _voucher_settings(pos_profile):
	row = frappe.db.get_value(
		"POS Profile", pos_profile,
		["mu_voucher_enabled", "mu_voucher_redeem_item", "mu_voucher_warehouse",
		 "mu_voucher_low_balance_threshold", "company"],
		as_dict=True,
	) or frappe._dict()
	# Daily limit is a newer custom field. Fetch it defensively so redemption
	# still works even if `bench migrate` has not yet added the DB column
	# (otherwise reading a missing column raises OperationalError).
	try:
		row["mu_voucher_daily_limit"] = frappe.db.get_value(
			"POS Profile", pos_profile, "mu_voucher_daily_limit"
		)
	except Exception:
		row["mu_voucher_daily_limit"] = 0
	# WhatsApp toggle is also a newer custom field; read it defensively and
	# default to ENABLED when the column is not there yet (migrate not run),
	# preserving the previous always-send behaviour.
	try:
		val = frappe.db.get_value("POS Profile", pos_profile, "mu_voucher_whatsapp_enabled")
		row["mu_voucher_whatsapp_enabled"] = 1 if val is None else cint(val)
	except Exception:
		row["mu_voucher_whatsapp_enabled"] = 1
	# OTP gate for redemption (sent to the CUSTOMER). Newer field; read safely.
	try:
		row["mu_voucher_otp_enabled"] = cint(
			frappe.db.get_value("POS Profile", pos_profile, "mu_voucher_otp_enabled")
		)
	except Exception:
		row["mu_voucher_otp_enabled"] = 0
	# Customizable OTP message templates (one per line, rotated at random).
	try:
		row["mu_otp_message_templates"] = frappe.db.get_value(
			"POS Profile", pos_profile, "mu_otp_message_templates"
		)
	except Exception:
		row["mu_otp_message_templates"] = None
	return row


def _redeemed_today(customer):
	"""Total voucher units already redeemed for a customer since local midnight."""
	today = frappe.utils.getdate()
	val = frappe.db.sql(
		"""
		select coalesce(sum(-quantity), 0)
		from `tabPrepaid Voucher Transaction`
		where customer = %s and transaction_type = 'Redeem'
		  and date(posting_datetime) = %s
		""",
		(customer, today),
	)
	return cint(val[0][0]) if val else 0


def _make_material_issue(item_code, warehouse, company, customer, qty=1, cost_center=None):
	"""Issue the physical units from stock for a redemption (no sales/VAT doc)."""
	se = frappe.new_doc("Stock Entry")
	se.stock_entry_type = "Material Issue"
	se.purpose = "Material Issue"
	se.company = company
	se.append("items", {
		"item_code": item_code,
		"qty": cint(qty) or 1,
		"s_warehouse": warehouse,
		"cost_center": cost_center,
		"allow_zero_valuation_rate": 1,
	})
	se.remarks = _("Prepaid voucher redemption for {0}").format(customer)
	se.insert(ignore_permissions=True)
	se.submit()
	return se.name


@frappe.whitelist()
def redeem_voucher(pos_profile, customer, pos_opening_shift, qty=1, otp_code=None, branch_address=None):
	"""Redeem one or more voucher units for the current customer.

	Decrements the balance by ``qty``, issues ``qty`` physical items from stock
	in a single Stock Entry, records a transaction bound to the open shift, and
	fires best-effort WhatsApp. No tax invoice is created — VAT was already
	collected at voucher-book purchase.

	When OTP protection is enabled for the profile, the first call (no
	``otp_code``) sends a code to the CUSTOMER's WhatsApp and returns
	``{"otp_required": True, ...}`` without redeeming; the second call carries
	the code, which is verified before anything is decremented.
	"""
	qty = cint(qty) or 1
	if qty <= 0:
		frappe.throw(_("Redemption quantity must be at least one."))
	if not customer:
		frappe.throw(_("Please select a customer before redeeming a voucher."))

	require_pos_profile_access(pos_profile)
	shift = require_shift_access(pos_opening_shift, pos_profile=pos_profile, require_open=True)

	cfg = _voucher_settings(pos_profile)
	if not cint(cfg.get("mu_voucher_enabled")):
		frappe.throw(_("The voucher system is not enabled for this POS Profile."))
	redeem_item = cfg.get("mu_voucher_redeem_item")
	if not redeem_item:
		frappe.throw(_("Configure the redemption item in the POS Profile first."))

	# The redemption item may be a SERVICE (e.g. "استبدال اسطوانة غاز") rather
	# than an inventoried product. A Stock Entry (Material Issue) is only valid
	# for a stock item, so we issue stock ONLY when the item is a stock item.
	# For a service item we simply decrement the voucher balance — no stock
	# movement, no warehouse needed. This is what caused the redemption to fail
	# with an opaque "Internal Server Error" when the item was a service.
	is_stock_item = cint(frappe.db.get_value("Item", redeem_item, "is_stock_item"))
	if is_stock_item and not cfg.get("mu_voucher_warehouse"):
		frappe.throw(_("Configure the redemption warehouse in the POS Profile first."))

	company = cfg.get("company") or shift.company

	# Look up branch-specific and general balance documents
	branch_bal_doc = None
	gen_bal_doc = None

	# If customer has active branch-dedicated vouchers, branch selection is mandatory
	has_branch_vouchers = bool(frappe.db.sql("""
		select 1 from `tabPrepaid Voucher Balance`
		where customer = %s and branch is not null and branch != '' and current_balance > 0
		limit 1
	""", customer))

	if has_branch_vouchers and not branch_address:
		frappe.throw(
			_("Selecting a branch/address is mandatory for this customer because they have branch-dedicated vouchers."),
			title=_("Branch Selection Required"),
		)

	if branch_address:
		branch_bal_name = frappe.db.get_value("Prepaid Voucher Balance", {"customer": customer, "branch": branch_address})
		if branch_bal_name:
			_lock_voucher_balance(branch_bal_name)
			branch_bal_doc = frappe.get_doc("Prepaid Voucher Balance", branch_bal_name)

	gen_name = frappe.db.get_value("Prepaid Voucher Balance", {"customer": customer, "is_general": 1})
	if not gen_name:
		gen_name = frappe.db.get_value("Prepaid Voucher Balance", {"customer": customer, "branch": ("in", ["", None])})
	if not gen_name and frappe.db.exists("Prepaid Voucher Balance", customer):
		gen_name = customer
	if gen_name:
		_lock_voucher_balance(gen_name)
		gen_bal_doc = frappe.get_doc("Prepaid Voucher Balance", gen_name)

	branch_avail = cint(branch_bal_doc.current_balance) if branch_bal_doc else 0
	gen_avail = cint(gen_bal_doc.current_balance) if gen_bal_doc else 0
	available = branch_avail + gen_avail

	if available <= 0:
		if branch_address and has_branch_vouchers:
			frappe.throw(_("This customer has no remaining voucher units for this branch."))
		frappe.throw(_("This customer has no remaining voucher units."))
	if qty > available:
		frappe.throw(_("Requested {0} vouchers but only {1} remain.").format(qty, available))

	# Anti-abuse: cap how many units one customer may redeem per day (0 = no cap).
	daily_limit = cint(cfg.get("mu_voucher_daily_limit"))
	if daily_limit > 0:
		used_today = _redeemed_today(customer)
		if used_today + qty > daily_limit:
			remaining_today = max(0, daily_limit - used_today)
			frappe.throw(_(
				"Daily redemption limit exceeded ({0} vouchers). Remaining allowed today: {1}."
			).format(daily_limit, remaining_today), frappe.ValidationError)

	# WhatsApp OTP gate (sent to branch if selected, otherwise to customer). All checks above have passed, so
	# we only send a code for a redemption that would otherwise succeed.
	if cint(cfg.get("mu_voucher_otp_enabled")):
		from pos_next.api import otp
		from pos_next.api.whatsapp_hook import get_branch_mobile, get_customer_mobile
		otp_ref = f"{pos_opening_shift}:{customer}:{branch_address}" if branch_address else f"{pos_opening_shift}:{customer}"
		if not otp_code:
			if branch_address:
				recipient_mobile = get_branch_mobile(branch_address)
				if not recipient_mobile:
					frappe.throw(
						_("No mobile number found for branch '{0}'. Please add a mobile/phone number to this branch address to send the verification code.").format(branch_address),
						title=_("Branch Phone Required"),
					)
			else:
				recipient_mobile = get_customer_mobile(customer)
				if not recipient_mobile:
					frappe.throw(
						_("No mobile number found for customer '{0}' to send the verification code.").format(customer),
						title=_("Customer Phone Required"),
					)

			return otp.generate_and_send(
				"voucher_redeem", otp_ref, recipient_mobile,
				label=_("Voucher Redemption"), digits=5,
				templates=cfg.get("mu_otp_message_templates"),
			)
		otp.verify("voucher_redeem", otp_ref, otp_code)

	# Physical hand-over first; if stock fails, nothing is decremented.
	try:
		# Only move stock for an inventoried item; a service redemption skips it.
		stock_entry = None
		if is_stock_item:
			stock_entry = _make_material_issue(
				redeem_item, cfg.get("mu_voucher_warehouse"),
				company, customer, qty=qty,
			)

		# Deduct from branch_bal_doc first, then gen_bal_doc for remainder
		qty_from_branch = min(qty, branch_avail)
		qty_from_gen = qty - qty_from_branch

		if qty_from_branch > 0 and branch_bal_doc:
			branch_bal_doc.total_redeemed = cint(branch_bal_doc.total_redeemed) + qty_from_branch
			branch_bal_doc.last_redeemed_on = now_datetime()
			branch_bal_doc.save(ignore_permissions=True)

		if qty_from_gen > 0 and gen_bal_doc:
			gen_bal_doc.total_redeemed = cint(gen_bal_doc.total_redeemed) + qty_from_gen
			gen_bal_doc.last_redeemed_on = now_datetime()
			gen_bal_doc.save(ignore_permissions=True)

		remaining = (cint(branch_bal_doc.current_balance) if branch_bal_doc else 0) + (cint(gen_bal_doc.current_balance) if gen_bal_doc else 0)

		_record_transaction(
			customer, -qty, "Redeem", remaining, company=company, pos_profile=pos_profile,
			pos_opening_shift=pos_opening_shift,
			reference_doctype="Stock Entry" if stock_entry else None,
			reference_name=stock_entry, stock_entry=stock_entry,
			branch=branch_address,
			remarks=_("Voucher redemption ({0}) - Branch: {1}").format(qty, branch_address) if branch_address else _("Voucher redemption ({0})").format(qty),
		)
	except frappe.ValidationError:
		# Clean, user-facing validation messages pass through unchanged.
		raise
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Voucher Redemption Failed")
		frappe.throw(
			_("Failed to redeem voucher: {0}").format(str(e)),
			title=_("Redemption Failed"),
		)

	# --- WhatsApp + low-balance alert (best-effort) ---
	# The redemption is already committed above; nothing in this tail may fail
	# the request. A WhatsApp/contact-lookup error must NOT surface as an
	# "Internal Server Error" after the balance was decremented and stock issued.
	low_alert = False
	whatsapp_on = cint(cfg.get("mu_voucher_whatsapp_enabled"))
	try:
		if whatsapp_on:
			cust_name = frappe.db.get_value("Customer", customer, "customer_name") or customer
			msg = _("Dear {0}, {1} vouchers have been redeemed. Your remaining balance is: {2} vouchers.").format(cust_name, qty, remaining)
			notify_customer(customer, msg, branch_address=branch_address)
			if branch_address:
				from pos_next.api.whatsapp_hook import get_branch_mobile, send_whatsapp
				br_phone = get_branch_mobile(branch_address)
				cust_phone = frappe.db.get_value("Customer", customer, "mobile_no")
				if br_phone and cust_phone and br_phone != cust_phone:
					send_whatsapp(cust_phone, msg)

			threshold = cint(cfg.get("mu_voucher_low_balance_threshold"))
			target_bal_doc = branch_bal_doc or gen_bal_doc
			if threshold > 0 and remaining <= threshold and target_bal_doc and not cint(getattr(target_bal_doc, "low_balance_notified", 0)):
				notify_customer(customer, _(
					"Notice: Your voucher balance is running low ({0} remaining). Please consider renewing your book."
				).format(remaining), branch_address=branch_address)
				target_bal_doc.db_set("low_balance_notified", 1)
				low_alert = True
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Voucher post-redemption notify failed")

	return {"customer": customer, "balance": remaining, "quantity": qty,
		"stock_entry": stock_entry, "low_balance_alert": low_alert}
