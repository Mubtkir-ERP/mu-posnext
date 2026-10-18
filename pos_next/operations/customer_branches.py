# -*- coding: utf-8 -*-
# Copyright (c) 2026, POS Next and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import nowdate, now_datetime, get_first_day, get_last_day, flt, cint
from pos_next.api.whatsapp_hook import send_whatsapp
import secrets
import json


@frappe.whitelist()
def get_customer_branches(customer):
    """
    Returns all branches (Addresses) linked to the given customer.
    If 0 or 1 branch, caller knows no disambiguation popup is needed.
    """
    if not customer:
        return []

    addresses = frappe.db.sql("""
        SELECT 
            addr.name,
            addr.address_title,
            addr.address_line1,
            addr.address_line2,
            addr.city,
            addr.phone,
            addr.email_id,
            addr.is_primary_address
        FROM `tabAddress` addr
        INNER JOIN `tabDynamic Link` dl ON dl.parent = addr.name
        WHERE dl.link_doctype = 'Customer' AND dl.link_name = %s
        ORDER BY addr.is_primary_address DESC, addr.creation ASC
    """, (customer,), as_dict=True)

    results = []
    for a in addresses:
        branch_label = a.address_title or a.address_line1 or a.name
        results.append({
            "address_name": a.name,
            "branch_title": branch_label,
            "address_line1": a.address_line1 or "",
            "city": a.city or "",
            "phone": a.phone or "",
            "email_id": a.email_id or "",
            "qr_data": f"MUBTKIR_BRANCH::{customer}::{a.name}"
        })

    return results


@frappe.whitelist()
def parse_branch_qr(qr_code_content):
    """
    Parses scanned QR Code content.
    Format: MUBTKIR_BRANCH::{customer}::{address_name} or JSON
    """
    if not qr_code_content:
        frappe.throw(_("Empty QR code"))

    qr_str = str(qr_code_content).strip()
    if qr_str.startswith("MUBTKIR_BRANCH::"):
        parts = qr_str.split("::")
        if len(parts) >= 3:
            return {
                "customer": parts[1],
                "branch_address": parts[2]
            }

    # Try JSON format
    try:
        data = json.loads(qr_str)
        if isinstance(data, dict) and "customer" in data:
            return data
    except Exception:
        pass

    frappe.throw(_("Invalid Branch QR Code format"))


@frappe.whitelist()
def create_branch_sales_order(customer, branch_address, items, pos_profile=None):
    """
    Creates an on-account (آجل) Sales Order from POS.
    Generates a 4-digit OTP and sends it via WhatsApp to branch phone for confirmation.
    """
    if not customer or not branch_address or not items:
        frappe.throw(_("Customer, Branch, and Items are required"))

    if isinstance(items, str):
        items = json.loads(items)

    profile_doc = frappe.get_cached_doc("POS Profile", pos_profile) if pos_profile else None
    company = profile_doc.company if profile_doc else frappe.defaults.get_user_default("Company")

    so = frappe.new_doc("Sales Order")
    so.customer = customer
    so.customer_address = branch_address
    so.shipping_address_name = branch_address
    so.company = company
    so.delivery_date = nowdate()
    so.transaction_date = nowdate()
    so.order_type = "Sales"

    for it in items:
        so.append("items", {
            "item_code": it["item_code"],
            "qty": flt(it["qty"]),
            "rate": flt(it.get("rate") or 0),
            "warehouse": it.get("warehouse") or (profile_doc.warehouse if profile_doc else None),
            "delivery_date": nowdate()
        })

    so.insert(ignore_permissions=True)

    # Generate 4-digit OTP
    otp = f"{secrets.randbelow(9000) + 1000}"
    cache_key = f"so_otp:{so.name}"
    frappe.cache.set_value(cache_key, otp, expires_in_sec=1800) # 30 mins

    # Get branch phone
    phone = frappe.db.get_value("Address", branch_address, "phone")
    if phone:
        msg = _("MUBTKIR: Your confirmation code for order {0} is {1}").format(so.name, otp)
        send_whatsapp(phone, msg)

    return {
        "status": "pending_otp",
        "sales_order": so.name,
        "phone": phone or "",
        "message": _("Sales Order {0} created. OTP sent to {1}").format(so.name, phone or _("customer phone"))
    }


@frappe.whitelist()
def confirm_branch_sales_order(sales_order, otp):
    """
    Verifies OTP and submits Sales Order.
    """
    cache_key = f"so_otp:{sales_order}"
    saved_otp = frappe.cache.get_value(cache_key)

    if not saved_otp or str(saved_otp).strip() != str(otp).strip():
        frappe.throw(_("Invalid or expired OTP code"), title=_("Verification Failed"))

    so = frappe.get_doc("Sales Order", sales_order)
    so.submit()
    frappe.cache.delete_value(cache_key)

    return {
        "status": "confirmed",
        "sales_order": so.name,
        "message": _("Sales Order {0} confirmed and submitted successfully").format(so.name)
    }


@frappe.whitelist()
def create_monthly_consolidated_invoice(customer, branch_address=None, from_date=None, to_date=None):
    """
    Consolidates all submitted unbilled Sales Orders for a customer/branch into a single monthly Sales Invoice.
    """
    if not from_date:
        from_date = get_first_day(nowdate())
    if not to_date:
        to_date = get_last_day(nowdate())

    filters = {
        "customer": customer,
        "docstatus": 1,
        "status": ["not in", ["Closed", "Completed", "Cancelled"]],
        "transaction_date": ["between", [from_date, to_date]],
        "per_billed": ["<", 100]
    }
    if branch_address:
        filters["shipping_address_name"] = branch_address

    sales_orders = frappe.get_all("Sales Order", filters=filters, pluck="name")
    if not sales_orders:
        frappe.throw(_("No unbilled Sales Orders found for this customer/branch in the selected period"))

    from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice

    # Create base invoice from the first order
    si = make_sales_invoice(sales_orders[0])
    
    # Merge items from subsequent sales orders
    for so_name in sales_orders[1:]:
        sub_si = make_sales_invoice(so_name)
        for it in sub_si.items:
            si.append("items", it)

    si.posting_date = to_date
    si.remarks = _("Monthly consolidated invoice for {0} ({1} to {2}) across {3} orders: {4}").format(
        customer, from_date, to_date, len(sales_orders), ", ".join(sales_orders[:5])
    )
    si.save(ignore_permissions=True)

    return {
        "status": "success",
        "sales_invoice": si.name,
        "consolidated_orders_count": len(sales_orders),
        "total_amount": si.grand_total
    }
