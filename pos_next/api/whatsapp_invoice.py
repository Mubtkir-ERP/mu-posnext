# -*- coding: utf-8 -*-
# Copyright (c) 2026, MUBTKIR and contributors
# For license information, please see license.txt

"""Send a submitted Sales Invoice summary to the customer over WhatsApp.

Best-effort: uses the shared WhatsApp seam (``mu_send_whatsapp`` hook or the
``mu_wats_api`` app). Gives the cashier a clear message when the customer has
no mobile number or WhatsApp is not connected yet.
"""

import frappe
from frappe import _
from frappe.utils import fmt_money

from pos_next.api.security import require_pos_profile_access
from pos_next.api.whatsapp_hook import send_whatsapp


def _customer_mobile(customer):
	mobile = frappe.db.get_value("Customer", customer, "mobile_no")
	if not mobile:
		mobile = frappe.db.get_value(
			"Contact",
			{"link_doctype": "Customer", "link_name": customer},
			"mobile_no",
		)
	return mobile


@frappe.whitelist()
def send_invoice_whatsapp(invoice, pos_profile=None):
	"""Send a short invoice summary to the invoice customer via WhatsApp."""
	if pos_profile:
		require_pos_profile_access(pos_profile)

	inv = frappe.get_doc("Sales Invoice", invoice)
	if not inv.get("customer"):
		frappe.throw(_("This invoice has no customer."))

	mobile = _customer_mobile(inv.customer)
	if not mobile:
		frappe.throw(_("لا يوجد رقم جوال لهذا العميل لإرسال الفاتورة."))

	cust_name = frappe.db.get_value("Customer", inv.customer, "customer_name") or inv.customer
	total = fmt_money(inv.grand_total, currency=inv.currency)
	message = _(
		"عزيزنا {0}، شكرًا لتعاملك مع {1}.\nفاتورتك رقم {2} بإجمالي {3}."
	).format(cust_name, inv.company, inv.name, total)

	sent = send_whatsapp(mobile, message)
	if not sent:
		frappe.throw(_("خدمة واتساب غير موصولة بعد. تم تسجيل الرسالة دون إرسال."))

	return {"ok": True, "invoice": inv.name}
