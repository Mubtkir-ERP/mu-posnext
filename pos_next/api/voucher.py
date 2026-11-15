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
from frappe.utils import add_days, cint, date_diff, getdate, now_datetime

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
		if frappe.db.has_column("POS Settings", "mu_voucher_enabled"):
			ps_val = frappe.db.get_value("POS Settings", {"pos_profile": pos_profile}, "mu_voucher_enabled")
			if ps_val is not None:
				enabled = cint(ps_val)
		if not enabled and frappe.db.has_column("POS Profile", "mu_voucher_enabled"):
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
	expiry_info = get_balance_expiry_info(customer, branch=branch)
	return {
		"customer": customer,
		"branch": branch,
		"balance": total,
		"general_balance": general_bal,
		"branch_balance": branch_bal,
		"has_branch_vouchers": has_branch_vouchers,
		"branch_balance_map": branch_balance_map,
		"enabled": enabled,
		"expiry_date": expiry_info.get("expiry_date"),
		"days_remaining": expiry_info.get("days_remaining"),
		"is_expired": expiry_info.get("is_expired", False),
	}


def get_balance_expiry_info(customer, branch=None):
	"""Return expiry_date (YYYY-MM-DD or None), days_remaining (int or None), and is_expired."""
	if not customer or not frappe.db.has_column("Prepaid Voucher Balance", "expiry_date"):
		return {"expiry_date": None, "days_remaining": None, "is_expired": False}

	filters = {"customer": customer, "current_balance": (">", 0)}
	if branch:
		filters["branch"] = branch
	rows = frappe.get_all(
		"Prepaid Voucher Balance",
		filters=filters,
		fields=["expiry_date"],
		order_by="expiry_date asc",
		limit_page_length=10,
	)
	if not rows and branch:
		rows = frappe.get_all(
			"Prepaid Voucher Balance",
			filters={"customer": customer, "is_general": 1, "current_balance": (">", 0)},
			fields=["expiry_date"],
			limit_page_length=5,
		)

	dates = [getdate(r.expiry_date) for r in rows if r.get("expiry_date")]
	if not dates:
		return {"expiry_date": None, "days_remaining": None, "is_expired": False}

	nearest = min(dates)
	days_left = date_diff(nearest, getdate())
	return {
		"expiry_date": str(nearest),
		"days_remaining": days_left,
		"is_expired": days_left < 0,
	}


def _expire_balance_doc(bal_doc, notify=True):
	"""Zero out an expired Prepaid Voucher Balance and record an Expire transaction."""
	if not bal_doc:
		return 0
	expired_qty = cint(bal_doc.current_balance)
	if expired_qty <= 0:
		if bal_doc.get("expiry_date"):
			bal_doc.expiry_date = None
			bal_doc.expiry_reminded = 0
			bal_doc.save(ignore_permissions=True)
		return 0

	bal_doc.total_expired = cint(bal_doc.get("total_expired")) + expired_qty
	bal_doc.expiry_date = None
	bal_doc.expiry_reminded = 0
	bal_doc.save(ignore_permissions=True)

	_record_transaction(
		bal_doc.customer,
		-expired_qty,
		"Expire",
		cint(bal_doc.current_balance),
		company=bal_doc.company,
		branch=bal_doc.branch,
		remarks=_("Voucher balance expired ({0} units)").format(expired_qty),
	)

	if notify:
		try:
			cust_name = frappe.db.get_value("Customer", bal_doc.customer, "customer_name") or bal_doc.customer
			msg = _("Dear {0}, your voucher package ({1} remaining units) has expired and the balance is now 0.").format(
				cust_name, expired_qty
			)
			notify_customer(bal_doc.customer, msg, branch_address=bal_doc.branch)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Voucher expiry notification failed")

	return expired_qty


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

def _voucher_purchase_info(doc):
	"""Return (total_units, max_validity_days) for voucher items in a Sales Invoice."""
	total = 0
	max_validity_days = 0
	has_validity_col = frappe.db.has_column("Item", "mu_voucher_validity_days")
	fields = ["mu_is_voucher_item", "mu_voucher_units"]
	if has_validity_col:
		fields.append("mu_voucher_validity_days")

	for row in doc.get("items", []):
		vals = frappe.db.get_value("Item", row.item_code, fields) or (0, 0)
		flag = cint(vals[0])
		units = cint(vals[1])
		validity = cint(vals[2]) if has_validity_col and len(vals) > 2 else 0
		if flag and units:
			total += units * cint(row.qty)
			if validity > max_validity_days:
				max_validity_days = validity
	return total, max_validity_days


def _voucher_units_in_invoice(doc):
	"""Sum voucher units sold in this invoice: qty * Item.mu_voucher_units."""
	total, _ = _voucher_purchase_info(doc)
	return total


def on_sales_invoice_submit(doc, method=None):
	"""Credit the customer's voucher balance when a voucher book is sold."""
	if not doc.get("customer"):
		return
	units, validity_days = _voucher_purchase_info(doc)
	if units <= 0:
		return

	# Determine branch allocation
	branch = None
	if doc.get("mu_voucher_branch_only") and doc.get("customer_address"):
		branch = doc.get("customer_address")

	bal = _get_or_create_balance(doc.customer, doc.company, branch=branch)

	# Clear any previously expired balance before crediting the new purchase
	if (
		cint(bal.current_balance) > 0
		and bal.get("expiry_date")
		and getdate(bal.expiry_date) < getdate()
	):
		_expire_balance_doc(bal, notify=False)

	bal.total_purchased = cint(bal.total_purchased) + units
	bal.low_balance_notified = 0  # topped up -> allow future low-balance alert

	if frappe.db.has_column("Prepaid Voucher Balance", "expiry_date"):
		if validity_days > 0:
			new_expiry = add_days(getdate(), validity_days)
			if bal.get("expiry_date") and getdate(bal.expiry_date) > new_expiry:
				pass
			else:
				bal.expiry_date = new_expiry
			bal.expiry_reminded = 0
		else:
			if not bal.get("expiry_date") or cint(bal.current_balance) <= 0:
				bal.expiry_date = None
				bal.expiry_reminded = 0

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

	# Best-effort WhatsApp notification with digital card link on purchase
	try:
		whatsapp_on = 1
		if doc.get("pos_profile"):
			cfg = _voucher_settings(doc.get("pos_profile"))
			whatsapp_on = cint(cfg.get("mu_voucher_whatsapp_enabled"))
		if whatsapp_on:
			from pos_next.operations.customer_branches import get_customer_card_url
			cust_name = frappe.db.get_value("Customer", doc.customer, "customer_name") or doc.customer
			card_url = get_customer_card_url(doc.customer, branch)
			expiry_text = (
				_(" Valid until: {0}.").format(bal.expiry_date)
				if bal.get("expiry_date")
				else ""
			)
			msg = _(
				"Dear {0}, {1} vouchers have been added to your account. Current balance: {2} vouchers.{3}\nDigital QR Card: {4}"
			).format(cust_name, units, cint(bal.current_balance), expiry_text, card_url)
			notify_customer(doc.customer, msg, branch_address=branch)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Voucher purchase WhatsApp notify failed")


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
	row = frappe._dict()
	row["company"] = frappe.db.get_value("POS Profile", pos_profile, "company")

	# Primary source: POS Settings (Special Apps section)
	ps_name = frappe.db.get_value("POS Settings", {"pos_profile": pos_profile}, "name")
	voucher_fields = [
		"mu_voucher_enabled",
		"mu_voucher_redeem_item",
		"mu_voucher_warehouse",
		"mu_voucher_low_balance_threshold",
		"mu_voucher_daily_limit",
		"mu_voucher_whatsapp_enabled",
		"mu_voucher_otp_enabled",
	]
	ps_has_voucher = ps_name and frappe.db.has_column("POS Settings", "mu_voucher_enabled")
	if ps_has_voucher:
		for f in voucher_fields:
			if frappe.db.has_column("POS Settings", f):
				row[f] = frappe.db.get_value("POS Settings", ps_name, f)

	# Backward-compatible fallback to POS Profile for any field not yet migrated/set
	for f in voucher_fields:
		if row.get(f) is None and frappe.db.has_column("POS Profile", f):
			row[f] = frappe.db.get_value("POS Profile", pos_profile, f)

	row["mu_voucher_enabled"] = cint(row.get("mu_voucher_enabled"))
	row["mu_voucher_low_balance_threshold"] = cint(row.get("mu_voucher_low_balance_threshold"))
	row["mu_voucher_daily_limit"] = cint(row.get("mu_voucher_daily_limit"))
	row["mu_voucher_whatsapp_enabled"] = 1 if row.get("mu_voucher_whatsapp_enabled") is None else cint(row.get("mu_voucher_whatsapp_enabled"))
	row["mu_voucher_otp_enabled"] = cint(row.get("mu_voucher_otp_enabled"))

	if frappe.db.has_column("POS Profile", "mu_otp_message_templates"):
		row["mu_otp_message_templates"] = frappe.db.get_value("POS Profile", pos_profile, "mu_otp_message_templates")
	else:
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

	# Auto-expire any expired balance before checking availability
	expired_any = False
	today = getdate()
	if branch_bal_doc and cint(branch_bal_doc.current_balance) > 0 and branch_bal_doc.get("expiry_date") and getdate(branch_bal_doc.expiry_date) < today:
		_expire_balance_doc(branch_bal_doc, notify=False)
		expired_any = True
	if gen_bal_doc and cint(gen_bal_doc.current_balance) > 0 and gen_bal_doc.get("expiry_date") and getdate(gen_bal_doc.expiry_date) < today:
		_expire_balance_doc(gen_bal_doc, notify=False)
		expired_any = True

	branch_avail = cint(branch_bal_doc.current_balance) if branch_bal_doc else 0
	gen_avail = cint(gen_bal_doc.current_balance) if gen_bal_doc else 0
	available = branch_avail + gen_avail

	if available <= 0:
		if expired_any:
			frappe.throw(_("This customer's voucher balance has expired."))
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


# ---------------------------------------------------------------------------
# Daily expiry & pre-expiry reminder scheduler
# ---------------------------------------------------------------------------

def _get_expiry_reminder_days():
	"""Return configured reminder days across enabled POS Settings/Profiles (default 3)."""
	if frappe.db.has_column("POS Settings", "mu_voucher_expiry_reminder_days") and frappe.db.has_column("POS Settings", "mu_voucher_enabled"):
		rows = frappe.get_all(
			"POS Settings",
			filters={"mu_voucher_enabled": 1},
			fields=["mu_voucher_expiry_reminder_days"],
		)
		vals = [cint(r.mu_voucher_expiry_reminder_days) for r in rows if cint(r.mu_voucher_expiry_reminder_days) > 0]
		if vals:
			return max(vals)
	if frappe.db.has_column("POS Profile", "mu_voucher_expiry_reminder_days") and frappe.db.has_column("POS Profile", "mu_voucher_enabled"):
		rows = frappe.get_all(
			"POS Profile",
			filters={"mu_voucher_enabled": 1},
			fields=["mu_voucher_expiry_reminder_days"],
		)
		vals = [cint(r.mu_voucher_expiry_reminder_days) for r in rows if cint(r.mu_voucher_expiry_reminder_days) > 0]
		if vals:
			return max(vals)
	return 3


@frappe.whitelist()
def process_voucher_expiries():
	"""Daily job:
	1. Zero out any Prepaid Voucher Balance past its expiry_date (records Expire txn).
	2. Send a WhatsApp reminder 3 days (configurable) before expiry_date.
	"""
	if not frappe.db.has_column("Prepaid Voucher Balance", "expiry_date"):
		return {"expired": 0, "reminded": 0}

	today = getdate()
	expired_count = 0
	reminded_count = 0

	# 1. Auto-expire past-due balances
	expired_rows = frappe.get_all(
		"Prepaid Voucher Balance",
		filters={
			"current_balance": (">", 0),
			"expiry_date": ["<", today],
		},
		pluck="name",
	)
	for name in expired_rows:
		try:
			_lock_voucher_balance(name)
			bal_doc = frappe.get_doc("Prepaid Voucher Balance", name)
			if cint(bal_doc.current_balance) > 0 and bal_doc.expiry_date and getdate(bal_doc.expiry_date) < today:
				_expire_balance_doc(bal_doc, notify=True)
				expired_count += 1
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"Voucher auto-expire failed for {name}")

	# 2. Send pre-expiry reminders (default 3 days before expiry)
	reminder_days = _get_expiry_reminder_days()
	if reminder_days > 0:
		cutoff_date = add_days(today, reminder_days)
		due_rows = frappe.get_all(
			"Prepaid Voucher Balance",
			filters={
				"current_balance": (">", 0),
				"expiry_date": ["between", [today, cutoff_date]],
				"expiry_reminded": 0,
			},
			fields=["name", "customer", "branch", "current_balance", "expiry_date"],
		)
		for row in due_rows:
			try:
				from pos_next.operations.customer_branches import get_customer_card_url
				cust_name = frappe.db.get_value("Customer", row.customer, "customer_name") or row.customer
				days_left = max(0, date_diff(getdate(row.expiry_date), today))
				card_url = get_customer_card_url(row.customer, row.branch)
				msg = _(
					"Reminder {0}: You have {1} voucher units expiring in {2} day(s) (on {3}). Use them before expiry.\nDigital QR Card: {4}"
				).format(cust_name, cint(row.current_balance), days_left, row.expiry_date, card_url)
				notify_customer(row.customer, msg, branch_address=row.branch)
				frappe.db.set_value("Prepaid Voucher Balance", row.name, "expiry_reminded", 1)
				reminded_count += 1
			except Exception:
				frappe.log_error(frappe.get_traceback(), f"Voucher expiry reminder failed for {row.name}")

	return {"expired": expired_count, "reminded": reminded_count}
