# -*- coding: utf-8 -*-
# Copyright (c) 2026, POS Next and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import nowdate, now_datetime, get_first_day, get_last_day, flt, cint
from pos_next.api.whatsapp_hook import send_whatsapp
import secrets
import json


import io
import base64


def generate_branch_qr_data_url(qr_text):
    """Generates base64 PNG data URL for QR code using qrcode library."""
    if not qr_text:
        return ""
    try:
        import qrcode

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=8,
            border=2,
        )
        qr.add_data(qr_text)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        return f"data:image/png;base64,{b64}"
    except Exception as e:
        frappe.log_error(f"Failed to generate QR code: {e}", "Customer Branch QR")
        return ""


@frappe.whitelist()
def get_customer_branches(customer):
    """
    Returns all branches (Addresses) linked to the given customer.
    Includes base64 QR code image for each branch.
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
        qr_text = f"MUBTKIR_BRANCH::{customer}::{a.name}"
        qr_img = generate_branch_qr_data_url(qr_text)
        results.append({
            "address_name": a.name,
            "branch_title": branch_label,
            "address_line1": a.address_line1 or "",
            "address_line2": a.address_line2 or "",
            "city": a.city or "",
            "phone": a.phone or "",
            "email_id": a.email_id or "",
            "is_primary": a.is_primary_address,
            "qr_data": qr_text,
            "qr_image": qr_img
        })

    return results


@frappe.whitelist()
def get_customer_branch_qr(customer, address_name):
    """
    Returns full QR info and card details for a customer branch.
    """
    if not customer or not address_name:
        frappe.throw(_("Customer and address are required"))

    customer_name = frappe.db.get_value("Customer", customer, "customer_name") or customer
    addr = frappe.get_doc("Address", address_name)
    qr_text = f"MUBTKIR_BRANCH::{customer}::{address_name}"
    qr_img = generate_branch_qr_data_url(qr_text)

    return {
        "customer": customer,
        "customer_name": customer_name,
        "address_name": address_name,
        "branch_title": addr.address_title or addr.address_line1 or address_name,
        "address_line1": addr.address_line1 or "",
        "city": addr.city or "",
        "phone": addr.phone or "",
        "qr_data": qr_text,
        "qr_image": qr_img
    }


@frappe.whitelist()
def get_branch_qr_card_html(customer, address_name):
    """
    Returns a styled, printable HTML card for customer branch QR.
    """
    info = get_customer_branch_qr(customer, address_name)
    qr_img = info.get("qr_image") or ""
    cust_name = info.get("customer_name") or customer
    branch_title = info.get("branch_title") or address_name
    city = info.get("city") or ""
    phone = info.get("phone") or ""
    addr_line = info.get("address_line1") or ""

    addr_info = f"📍 {addr_line} {city}" if (addr_line or city) else ""
    phone_info = f"📞 {phone}" if phone else ""

    html = f"""<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="utf-8">
    <title>بطاقة فرع العميل - {cust_name}</title>
    <style>
        @media print {{
            body {{ margin: 0; padding: 0; background: white; }}
            .no-print {{ display: none !important; }}
            .card {{ box-shadow: none !important; border: 1px solid #ccc !important; }}
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background-color: #f3f4f6;
            margin: 0;
            padding: 30px 15px;
            display: flex;
            flex-direction: column;
            align-items: center;
        }}
        .card {{
            background: white;
            border: 2px solid #e5e7eb;
            border-radius: 16px;
            padding: 24px;
            width: 300px;
            text-align: center;
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
        }}
        .customer-name {{
            font-size: 17px;
            font-weight: 700;
            color: #111827;
            margin-bottom: 6px;
            line-height: 1.3;
        }}
        .branch-badge {{
            display: inline-block;
            background: #eff6ff;
            color: #1d4ed8;
            padding: 4px 14px;
            border-radius: 9999px;
            font-size: 13px;
            font-weight: 600;
            margin-bottom: 16px;
            border: 1px solid #bfdbfe;
        }}
        .qr-wrapper {{
            background: #fafafa;
            border: 1px dashed #d1d5db;
            border-radius: 12px;
            padding: 12px;
            display: inline-block;
            margin-bottom: 14px;
        }}
        .qr-img {{
            width: 190px;
            height: 190px;
            display: block;
        }}
        .info-row {{
            font-size: 12px;
            color: #4b5563;
            margin-top: 4px;
        }}
        .scan-hint {{
            font-size: 11px;
            color: #9ca3af;
            margin-top: 14px;
            border-top: 1px solid #f3f4f6;
            padding-top: 10px;
        }}
        .print-btn {{
            background: #2563eb;
            color: white;
            border: none;
            padding: 10px 24px;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            margin-top: 20px;
            box-shadow: 0 2px 4px rgba(37, 99, 235, 0.2);
            transition: all 0.2s;
        }}
        .print-btn:hover {{
            background: #1d4ed8;
            transform: translateY(-1px);
        }}
    </style>
</head>
<body>
    <div class="card">
        <div class="customer-name">{cust_name}</div>
        <div class="branch-badge">🏢 {branch_title}</div>
        <div class="qr-wrapper">
            <img src="{qr_img}" alt="Branch QR Code" class="qr-img" />
        </div>
        <div class="info-row">{addr_info}</div>
        <div class="info-row">{phone_info}</div>
        <div class="scan-hint">امسح الكود لتحديد العميل وفرعه تلقائياً في نقاط البيع</div>
    </div>
    <button class="print-btn no-print" onclick="window.print()">طباعة البطاقة / الملصق 🖨️</button>
</body>
</html>"""
    return html


@frappe.whitelist()
def resolve_customer_branch(qr_code_content):
    """
    Parses scanned QR and returns full customer and branch details for instant POS selection.
    """
    parsed = parse_branch_qr(qr_code_content)
    customer_name = parsed.get("customer")
    branch_address = parsed.get("branch_address")

    if not frappe.db.exists("Customer", customer_name):
        frappe.throw(_("Customer {0} not found").format(customer_name))

    customer_doc = frappe.get_doc("Customer", customer_name)
    branch_doc = frappe.get_doc("Address", branch_address) if branch_address and frappe.db.exists("Address", branch_address) else None

    branch_title = ""
    if branch_doc:
        branch_title = branch_doc.address_title or branch_doc.address_line1 or branch_doc.name

    return {
        "status": "success",
        "customer": {
            "name": customer_doc.name,
            "customer_name": customer_doc.customer_name,
            "customer_group": customer_doc.customer_group,
            "territory": customer_doc.territory,
            "mobile_no": customer_doc.mobile_no,
            "email_id": customer_doc.email_id,
        },
        "branch_address": branch_address,
        "branch_title": branch_title,
        "branch_city": branch_doc.city if branch_doc else "",
        "branch_phone": branch_doc.phone if branch_doc else ""
    }


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
