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

To connect it later, either add to the WhatsApp app's hooks.py:
    mu_send_whatsapp = ["mu_wats_api.api.send_text"]
or implement `send_text(mobile_no, message)` in that app.
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

		# 2) Try the MUBTKIR WhatsApp app directly, if present.
		try:
			from mu_wats_api.api import send_text  # type: ignore

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


def notify_customer(customer, message):
	"""Resolve a customer's mobile and send a WhatsApp message (best-effort)."""
	if not customer or not message:
		return False
	mobile = frappe.db.get_value("Customer", customer, "mobile_no")
	if not mobile:
		contact = frappe.db.get_value(
			"Contact",
			{"link_doctype": "Customer", "link_name": customer},
			"mobile_no",
		)
		mobile = contact
	if not mobile:
		return False
	return send_whatsapp(mobile, message)
