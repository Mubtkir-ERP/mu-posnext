# -*- coding: utf-8 -*-
# Copyright (c) 2026, POS Next and contributors
# For license information, please see license.txt

"""Pluggable WhatsApp send hook.

This is a thin, dependency-free seam. It tries, in order:
  1. Any app-provided hook registered under `mu_send_whatsapp` in hooks.py
     (each value is a dotted path to `fn(mobile_no, message)`).
  2. A direct call into the MUBTKIR WhatsApp app if it is installed.
If neither is available the message is logged and silently skipped, so the
voucher flow never fails because WhatsApp is not wired yet.

To connect it later, add to the WhatsApp app's (frappe_whatsapp) hooks.py:
    mu_send_whatsapp = ["frappe_whatsapp.api.send_text"]
where that app exposes `send_text(mobile_no=..., message=...)`.
"""

import frappe


def send_whatsapp(mobile_no, message):
	"""Best-effort WhatsApp send. Never raises into the caller."""
	if not mobile_no or not message:
		return False
	try:
		# 1) Registered hooks take priority.
		for method in frappe.get_hooks("mu_send_whatsapp") or []:
			try:
				frappe.call(method, mobile_no=mobile_no, message=message)
				return True
			except Exception:
				frappe.log_error(frappe.get_traceback(), "mu_send_whatsapp hook failed")

		# 2) Try the WhatsApp app (frappe_whatsapp) directly, if present.
		try:
			from frappe_whatsapp.api import send_text  # type: ignore

			send_text(mobile_no=mobile_no, message=message)
			return True
		except Exception:
			pass

		# 3) Not wired yet — record and move on.
		frappe.logger("pos_next.voucher").info(
			f"WhatsApp not wired; skipped message to {mobile_no}: {message[:80]}"
		)
		return False
	except Exception:
		frappe.log_error(frappe.get_traceback(), "send_whatsapp unexpected error")
		return False


def get_customer_mobile(customer):
	"""Return a customer's best-known mobile number, or '' if none.

	`mobile_no` on Customer is often empty; the number lives on the linked
	primary Contact, reached through the Dynamic Link child table.
	`link_doctype`/`link_name` are columns of `Dynamic Link`, NOT of `Contact`,
	so filtering Contact by them raised
	OperationalError(1054, "Unknown column 'link_doctype'").
	"""
	if not customer:
		return ""
	try:
		mobile = frappe.db.get_value("Customer", customer, "mobile_no")
		if not mobile:
			contact_name = frappe.db.get_value(
				"Dynamic Link",
				{"link_doctype": "Customer", "link_name": customer, "parenttype": "Contact"},
				"parent",
			)
			if contact_name:
				mobile = frappe.db.get_value("Contact", contact_name, "mobile_no")
		return mobile or ""
	except Exception:
		frappe.log_error(frappe.get_traceback(), "get_customer_mobile failed")
		return ""


def notify_customer(customer, message):
	"""Resolve a customer's mobile and send a WhatsApp message (best-effort).

	Never raises into the caller — the redemption/voucher flow must not fail
	because of WhatsApp or a contact lookup.
	"""
	if not customer or not message:
		return False
	try:
		mobile = get_customer_mobile(customer)
		if not mobile:
			return False
		return send_whatsapp(mobile, message)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "notify_customer failed")
		return False
