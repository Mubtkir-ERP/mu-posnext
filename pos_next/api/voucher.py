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

def _get_or_create_balance(customer, company=None):
	name = frappe.db.exists("Prepaid Voucher Balance", {"customer": customer})
	if name:
		return frappe.get_doc("Prepaid Voucher Balance", name)
	doc = frappe.new_doc("Prepaid Voucher Balance")
	doc.customer = customer
	doc.company = company
	doc.total_purchased = 0
	doc.total_redeemed = 0
	doc.insert(ignore_permissions=True)
	return doc


def get_balance_value(customer):
	"""Current remaining units for a customer (0 if none)."""
	if not customer:
		return 0
	val = frappe.db.get_value("Prepaid Voucher Balance", {"customer": customer}, "current_balance")
	return cint(val)


@frappe.whitelist()
def get_voucher_balance(customer, pos_profile=None):
	"""Public: current balance + whether the voucher system is enabled."""
	enabled = 0
	if pos_profile:
		require_pos_profile_access(pos_profile)
		enabled = cint(frappe.db.get_value("POS Profile", pos_profile, "mu_voucher_enabled"))
	return {
		"customer": customer,
		"balance": get_balance_value(customer) if customer else 0,
		"enabled": enabled,
	}


def _record_transaction(customer, qty, txn_type, balance_after, company=None,
	pos_profile=None, pos_opening_shift=None, reference_doctype=None,
	reference_name=None, stock_entry=None, remarks=None):
	txn = frappe.new_doc("Prepaid Voucher Transaction")
	txn.customer = customer
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
	bal = _get_or_create_balance(doc.customer, doc.company)
	bal.total_purchased = cint(bal.total_purchased) + units
	bal.low_balance_notified = 0  # topped up -> allow future low-balance alert
	bal.save(ignore_permissions=True)
	_record_transaction(
		doc.customer, units, "Purchase", cint(bal.current_balance),
		company=doc.company, pos_profile=doc.get("pos_profile"),
		reference_doctype="Sales Invoice", reference_name=doc.name,
		remarks=_("Voucher book purchase"),
	)


def on_sales_invoice_cancel(doc, method=None):
	"""Reverse the credited units if a voucher-book invoice is cancelled."""
	if not doc.get("customer"):
		return
	units = _voucher_units_in_invoice(doc)
	if units <= 0:
		return
	name = frappe.db.exists("Prepaid Voucher Balance", {"customer": doc.customer})
	if not name:
		return
	bal = frappe.get_doc("Prepaid Voucher Balance", name)
	bal.total_purchased = max(0, cint(bal.total_purchased) - units)
	bal.save(ignore_permissions=True)
	_record_transaction(
		doc.customer, -units, "Purchase", cint(bal.current_balance),
		company=doc.company, pos_profile=doc.get("pos_profile"),
		reference_doctype="Sales Invoice", reference_name=doc.name,
		remarks=_("Reversal of cancelled voucher-book invoice"),
	)


# ---------------------------------------------------------------------------
# Redemption side — POS action (no tax invoice)
# ---------------------------------------------------------------------------

def _voucher_settings(pos_profile):
	row = frappe.db.get_value(
		"POS Profile", pos_profile,
		["mu_voucher_enabled", "mu_voucher_redeem_item", "mu_voucher_warehouse",
		 "mu_voucher_low_balance_threshold", "mu_voucher_daily_limit", "company"],
		as_dict=True,
	)
	return row or frappe._dict()


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
def redeem_voucher(pos_profile, customer, pos_opening_shift, qty=1):
	"""Redeem one or more voucher units for the current customer.

	Decrements the balance by ``qty``, issues ``qty`` physical items from stock
	in a single Stock Entry, records a transaction bound to the open shift, and
	fires best-effort WhatsApp. No tax invoice is created — VAT was already
	collected at voucher-book purchase.
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
	if not cfg.get("mu_voucher_redeem_item"):
		frappe.throw(_("Configure the redemption item in the POS Profile first."))
	if not cfg.get("mu_voucher_warehouse"):
		frappe.throw(_("Configure the redemption warehouse in the POS Profile first."))

	company = cfg.get("company") or shift.company

	name = frappe.db.exists("Prepaid Voucher Balance", {"customer": customer})
	if not name:
		frappe.throw(_("This customer has no voucher balance."))
	bal = frappe.get_doc("Prepaid Voucher Balance", name)
	# File-level lock prevents concurrent over-redemption without holding a raw
	# DB row lock (which could surface as a lock-wait OperationalError).
	bal.lock()
	available = cint(bal.current_balance)
	if available <= 0:
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
				"تجاوز الحد اليومي للاستبدال ({0} قسيمة). المتبقي المسموح اليوم: {1}."
			).format(daily_limit, remaining_today), frappe.ValidationError)

	# Physical hand-over first; if stock fails, nothing is decremented.
	stock_entry = _make_material_issue(
		cfg.get("mu_voucher_redeem_item"), cfg.get("mu_voucher_warehouse"),
		company, customer, qty=qty,
	)

	bal.total_redeemed = cint(bal.total_redeemed) + qty
	bal.last_redeemed_on = now_datetime()
	bal.save(ignore_permissions=True)
	remaining = cint(bal.current_balance)

	_record_transaction(
		customer, -qty, "Redeem", remaining, company=company, pos_profile=pos_profile,
		pos_opening_shift=pos_opening_shift, reference_doctype="Stock Entry",
		reference_name=stock_entry, stock_entry=stock_entry,
		remarks=_("Voucher redemption ({0})").format(qty),
	)

	# --- WhatsApp (best-effort) ---
	cust_name = frappe.db.get_value("Customer", customer, "customer_name") or customer
	notify_customer(customer, _(
		"عزيزنا {0}، تم استخدام {1} قسيمة. رصيدك المتبقي: {2} قسيمة."
	).format(cust_name, qty, remaining))

	threshold = cint(cfg.get("mu_voucher_low_balance_threshold"))
	low_alert = False
	if threshold > 0 and remaining <= threshold and not cint(bal.low_balance_notified):
		notify_customer(customer, _(
			"تنبيه: رصيد قسائمك قارب على الانتهاء ({0} متبقية). يسعدنا تجديد دفترك."
		).format(remaining))
		bal.db_set("low_balance_notified", 1)
		low_alert = True

	return {"customer": customer, "balance": remaining, "quantity": qty,
		"stock_entry": stock_entry, "low_balance_alert": low_alert}
