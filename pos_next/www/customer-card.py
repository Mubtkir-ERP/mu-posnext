# -*- coding: utf-8 -*-
# Copyright (c) 2026, Mubtkir and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import cint
from pos_next.operations.customer_branches import (
    verify_customer_card_token,
    get_customer_qr_card_data,
)

no_cache = 1


def get_context(context):
    context.no_cache = 1
    customer = (frappe.form_dict.get("customer") or "").strip()
    branch = (frappe.form_dict.get("branch") or "").strip() or None
    token = (frappe.form_dict.get("token") or "").strip()

    is_system_user = (
        frappe.session.user != "Guest"
        and frappe.db.get_value("User", frappe.session.user, "user_type") == "System User"
    )

    if not customer or not frappe.db.exists("Customer", customer):
        context.authorized = False
        context.error_message = _("Customer record not found.")
        return

    if not is_system_user and not verify_customer_card_token(customer, token, branch):
        context.authorized = False
        context.error_message = _("Invalid or expired card link. Please request a new QR card from the store.")
        return

    card_data = get_customer_qr_card_data(customer, branch)
    context.authorized = True
    context.company_name = card_data.get("company_name") or "Mubtkir ERP"
    context.customer = card_data.get("customer")
    context.customer_name = card_data.get("customer_name")
    context.branch_title = card_data.get("branch_title")
    context.address_line1 = card_data.get("address_line1")
    context.city = card_data.get("city")
    context.voucher_balance = cint(card_data.get("voucher_balance", 0))
    context.expiry_date = card_data.get("expiry_date")
    context.days_remaining = card_data.get("days_remaining")
    context.qr_image = card_data.get("qr_image")

    transactions = []
    if frappe.db.exists("DocType", "Prepaid Voucher Transaction"):
        filters = {"customer": customer}
        if branch and frappe.db.has_column("Prepaid Voucher Transaction", "branch"):
            filters["branch"] = branch
        raw_txns = frappe.db.get_all(
            "Prepaid Voucher Transaction",
            filters=filters,
            fields=["transaction_type", "quantity", "balance_after", "posting_datetime", "reference_name"],
            order_by="creation desc",
            limit_page_length=10,
        )
        for t in raw_txns:
            transactions.append({
                "txn_type": t.transaction_type,
                "qty": t.quantity,
                "balance_after": t.balance_after,
                "posting_date": str(t.posting_datetime)[:10] if t.posting_datetime else "",
                "reference_name": t.reference_name,
            })
    context.transactions = transactions
