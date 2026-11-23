# -*- coding: utf-8 -*-
# Copyright (c) 2026, POS Next and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import nowdate, now_datetime, get_first_day, get_last_day, flt, cint
from pos_next.api.whatsapp_hook import send_whatsapp
from pos_next.api.security import require_pos_profile_access
import secrets
import json


import io
import base64


def generate_branch_qr_data_url(qr_text):
    """Generates vector SVG or PNG base64 data URL for QR code with zero external dependencies."""
    if not qr_text:
        return ""

    # Priority 1: Vendored pyqrcode (100% pure Python, zero dependencies, crisp vector SVG)
    try:
        from pos_next.operations import pyqrcode
        qr = pyqrcode.create(qr_text, error='M', encoding='utf-8')
        buf = io.BytesIO()
        qr.svg(buf, scale=5)
        svg_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        return f"data:image/svg+xml;base64,{svg_b64}"
    except Exception as e:
        frappe.log_error(f"Vendored pyqrcode failed: {e}", "Customer Branch QR")

    # Priority 2: System pyqrcode if available
    try:
        import pyqrcode
        qr = pyqrcode.create(qr_text, error='M', encoding='utf-8')
        buf = io.BytesIO()
        qr.svg(buf, scale=5)
        svg_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        return f"data:image/svg+xml;base64,{svg_b64}"
    except Exception:
        pass

    # Priority 3: qrcode library if installed
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
    except Exception:
        pass

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
def get_all_branches_qr_cards_html(customer):
    """
    Returns a styled, printable HTML containing unified A6 QR stickers for all branches of a customer.
    """
    branches = get_customer_branches(customer)
    if not branches:
        frappe.throw(_("No linked addresses/branches found for this customer. Please add an address first."))

    company_name = (
        frappe.defaults.get_user_default("Company")
        or frappe.db.get_single_value("Global Defaults", "default_company")
        or ""
    )
    cust_name = frappe.db.get_value("Customer", customer, "customer_name") or customer
    cards_html = []
    for b in branches:
        qr_img = b.get("qr_image") or ""
        branch_title = frappe.utils.escape_html(b.get("branch_title") or b.get("address_name") or "")
        city = frappe.utils.escape_html(b.get("city") or "")
        addr_line = frappe.utils.escape_html(b.get("address_line1") or "")
        addr_text = " ".join(part for part in (addr_line, city) if part)
        addr_html = f'<div class="address-line">📍 {addr_text}</div>' if addr_text else ""
        company_esc = frappe.utils.escape_html(company_name or "")
        company_html = f'<div class="company-name">{company_esc}</div>' if company_esc else ""

        cards_html.append(f"""
        <div class="a6-sticker">
            <div class="a6-card">
                <div style="width:100%;">
                    {company_html}
                    <div class="customer-name">{branch_title}</div>
                    {addr_html}
                </div>
                <div class="qr-box">
                    <img src="{qr_img}" alt="Customer QR Code" />
                </div>
                <div class="a6-footer">Powered By MUBTKIR ERP</div>
            </div>
        </div>
        """)

    all_cards_str = "\n".join(cards_html)
    cust_name_esc = frappe.utils.escape_html(cust_name or "")
    return f"""<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="utf-8">
    <title>{_("Customer QR Card")} - {cust_name_esc}</title>
    <style>
        @page {{
            size: A6 portrait;
            margin: 0;
        }}
        * {{
            box-sizing: border-box;
        }}
        html, body {{
            margin: 0;
            padding: 0;
            font-family: sans-serif;
            direction: rtl;
            background: #fff;
        }}
        .no-print {{
            text-align: center;
            padding: 12px;
            background: #f8fafc;
            border-bottom: 1px solid #e2e8f0;
        }}
        .no-print button {{
            padding: 8px 20px;
            font-size: 14px;
            font-weight: 700;
            cursor: pointer;
            background: #0f172a;
            color: #fff;
            border: none;
            border-radius: 6px;
        }}
        .a6-sticker {{
            width: 105mm;
            height: 148mm;
            padding: 5mm;
            margin: 0 auto;
            page-break-after: always;
            display: flex;
        }}
        .a6-sticker:last-child {{
            page-break-after: auto;
        }}
        .a6-card {{
            width: 100%;
            height: 100%;
            border: 4px solid #F28C28;
            border-radius: 14px;
            padding: 7mm 5mm;
            display: flex;
            flex-direction: column;
            align-items: center;
            text-align: center;
            justify-content: space-between;
            overflow: hidden;
        }}
        .company-name {{
            font-size: 20px;
            font-weight: 900;
            color: #111827;
            margin-bottom: 12px;
        }}
        .customer-name {{
            font-size: 23px;
            font-weight: 800;
            color: #111827;
            margin: 10px 0;
        }}
        .address-line {{
            font-size: 15px;
            font-weight: 600;
            color: #475569;
            margin-top: 12px;
            line-height: 1.7;
        }}
        .qr-box {{
            width: 82mm;
            height: 82mm;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: auto;
        }}
        .qr-box img {{
            width: 100%;
            height: 100%;
            object-fit: contain;
        }}
        .a6-footer {{
            width: 100%;
            text-align: center;
            font-size: 9px;
            font-weight: 600;
            color: #999999;
            padding-top: 5px;
        }}
        @media print {{
            .no-print {{ display: none !important; }}
            html, body {{
                width: 105mm;
                height: 148mm;
            }}
        }}
    </style>
</head>
<body>
    <div class="no-print">
        <button onclick="window.print()">🖨️ {_("Print All Branch Cards")}</button>
    </div>
    {all_cards_str}
</body>
</html>"""


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

    profile_doc = None
    if pos_profile:
        require_pos_profile_access(pos_profile)
        profile_doc = frappe.get_cached_doc("POS Profile", pos_profile)

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

    dn_name = None
    try:
        from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note
        dn = make_delivery_note(so.name)
        dn.flags.ignore_permissions = True
        dn.insert(ignore_permissions=True)
        dn.submit()
        dn_name = dn.name
    except Exception as dn_err:
        frappe.log_error(f"Failed to auto-create Delivery Note for {so.name}: {dn_err}", "Gas Auto Delivery Note")

    return {
        "status": "confirmed",
        "sales_order": so.name,
        "delivery_note": dn_name,
        "message": _("Sales Order {0} and Delivery Note {1} confirmed successfully").format(so.name, dn_name or "") if dn_name else _("Sales Order {0} confirmed successfully").format(so.name)
    }


@frappe.whitelist()
def resolve_customer_qr(qr_text, pos_profile=None):
    """Resolve customer and branch from scanned QR code string.

    Supports:
    - MUBTKIR_BRANCH::{customer}::{branch}
    - Web URL with ?customer=...&branch=...
    - Query string customer=...&branch=...
    - JSON object {"customer": ..., "branch": ...}
    - Direct Customer name, customer_name, or mobile_no
    """
    import urllib.parse
    import json

    if not qr_text or not isinstance(qr_text, str):
        frappe.throw(_("Invalid QR Code content"), title=_("Scan Error"))

    text = qr_text.strip()
    cust_param = None
    branch_param = None

    # Pattern 1: MUBTKIR_BRANCH::{customer}::{branch} or MUBTKIR_CUSTOMER::{customer}
    if text.startswith("MUBTKIR_BRANCH::") or text.startswith("MUBTKIR_CUSTOMER::"):
        parts = text.split("::")
        if len(parts) >= 2:
            cust_param = parts[1].strip()
        if len(parts) >= 3:
            branch_param = parts[2].strip()

    # Pattern 2: URL containing customer query parameter
    elif "?" in text or text.startswith("http://") or text.startswith("https://") or "/gas-delivery" in text or "/customer-card" in text:
        try:
            url_to_parse = text if text.startswith("http") else f"http://dummy.local/{text.lstrip('/')}"
            parsed = urllib.parse.urlparse(url_to_parse)
            qs = urllib.parse.parse_qs(parsed.query)
            if "customer" in qs:
                cust_param = qs["customer"][0].strip()
            if "branch" in qs:
                branch_param = qs["branch"][0].strip()
        except Exception:
            pass

    # Pattern 3: Key-value query string (customer=...&branch=...)
    elif "customer=" in text:
        try:
            qs = urllib.parse.parse_qs(text)
            if "customer" in qs:
                cust_param = qs["customer"][0].strip()
            if "branch" in qs:
                branch_param = qs["branch"][0].strip()
        except Exception:
            pass

    # Pattern 4: JSON string
    elif text.startswith("{") and text.endswith("}"):
        try:
            data = json.loads(text)
            cust_param = data.get("customer")
            branch_param = data.get("branch")
        except Exception:
            pass

    # Pattern 5: Raw text fallback
    if not cust_param:
        cust_param = text

    # Look up Customer in Database
    # Try by name (ID)
    customer_doc = frappe.db.get_value(
        "Customer",
        {"name": cust_param},
        ["name", "customer_name", "mobile_no", "customer_group", "territory", "tax_id"],
        as_dict=True,
    )
    # If not found by name, try customer_name
    if not customer_doc:
        customer_doc = frappe.db.get_value(
            "Customer",
            {"customer_name": cust_param},
            ["name", "customer_name", "mobile_no", "customer_group", "territory", "tax_id"],
            as_dict=True,
        )
    # If not found, try mobile_no
    if not customer_doc:
        customer_doc = frappe.db.get_value(
            "Customer",
            {"mobile_no": cust_param},
            ["name", "customer_name", "mobile_no", "customer_group", "territory", "tax_id"],
            as_dict=True,
        )

    if not customer_doc:
        frappe.throw(
            _("No customer found matching '{0}'").format(cust_param),
            title=_("Customer Not Found"),
        )

    actual_customer = customer_doc["name"]

    # Match Branch / Address if provided
    matched_branch = None
    branch_title = None

    if branch_param:
        addr = frappe.db.sql("""
            SELECT addr.name, addr.address_title, addr.phone
            FROM `tabAddress` addr
            INNER JOIN `tabDynamic Link` dl ON dl.parent = addr.name
            WHERE dl.link_doctype = 'Customer' AND dl.link_name = %s
              AND (addr.name = %s OR addr.address_title = %s)
            LIMIT 1
        """, (actual_customer, branch_param, branch_param), as_dict=True)

        if addr:
            matched_branch = addr[0]["name"]
            branch_title = addr[0]["address_title"] or addr[0]["name"]
        else:
            addr_like = frappe.db.sql("""
                SELECT addr.name, addr.address_title, addr.phone
                FROM `tabAddress` addr
                INNER JOIN `tabDynamic Link` dl ON dl.parent = addr.name
                WHERE dl.link_doctype = 'Customer' AND dl.link_name = %s
                  AND addr.address_title LIKE %s
                LIMIT 1
            """, (actual_customer, f"%{branch_param}%"), as_dict=True)
            if addr_like:
                matched_branch = addr_like[0]["name"]
                branch_title = addr_like[0]["address_title"] or addr_like[0]["name"]

    # If no branch matched or specified, check if customer has a single/primary branch
    if not matched_branch:
        default_addr = frappe.db.sql("""
            SELECT addr.name, addr.address_title
            FROM `tabAddress` addr
            INNER JOIN `tabDynamic Link` dl ON dl.parent = addr.name
            WHERE dl.link_doctype = 'Customer' AND dl.link_name = %s
            ORDER BY addr.is_primary_address DESC, addr.creation ASC
            LIMIT 1
        """, (actual_customer,), as_dict=True)
        if default_addr:
            matched_branch = default_addr[0]["name"]
            branch_title = default_addr[0]["address_title"] or default_addr[0]["name"]

    # Fetch voucher balance
    from pos_next.api.voucher import get_voucher_balance
    voucher_info = get_voucher_balance(actual_customer, pos_profile=pos_profile, branch=matched_branch)
    voucher_balance = cint(voucher_info.get("balance", 0))

    return {
        "success": True,
        "customer": customer_doc,
        "branch": matched_branch,
        "branch_title": branch_title or matched_branch,
        "voucher_balance": voucher_balance,
        "has_branch_vouchers": bool(voucher_info.get("has_branch_vouchers")),
        "voucher_info": voucher_info,
    }


def _get_card_hmac_secret():
    """Return a site-scoped secret key for signing customer digital card URLs."""
    return str(frappe.local.conf.get("encryption_key") or frappe.local.site or "mubtkir-erp-card")


def generate_customer_card_token(customer, address_name=None):
    """Generate a deterministic HMAC-SHA256 token for customer digital voucher card access."""
    import hmac
    import hashlib

    payload = f"{customer or ''}::{address_name or ''}".encode("utf-8")
    secret = _get_card_hmac_secret().encode("utf-8")
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()[:24]


def verify_customer_card_token(customer, token, address_name=None):
    """Verify the HMAC token for customer digital voucher card access."""
    import hmac

    if not customer or not token:
        return False
    expected = generate_customer_card_token(customer, address_name)
    return hmac.compare_digest(str(expected), str(token))


def get_customer_card_url(customer, address_name=None):
    """Build the signed public URL for the customer digital voucher balance & QR page."""
    import urllib.parse

    site_url = (frappe.utils.get_url() or "").rstrip("/")
    token = generate_customer_card_token(customer, address_name)
    params = {"customer": customer or "", "token": token}
    if address_name:
        params["branch"] = address_name
    return f"{site_url}/customer-card?{urllib.parse.urlencode(params)}"


@frappe.whitelist()
def get_customer_qr_card_data(customer, address_name=None):
    """Return unified QR card data (customer/branch, company name, voucher balance, digital card URL)."""
    if not customer or not frappe.db.exists("Customer", customer):
        frappe.throw(_("Customer not found"))

    company_name = (
        frappe.defaults.get_user_default("Company")
        or frappe.db.get_single_value("Global Defaults", "default_company")
        or ""
    )
    customer_name = frappe.db.get_value("Customer", customer, "customer_name") or customer

    branch_title = ""
    address_line1 = ""
    city = ""
    phone = ""

    if address_name and frappe.db.exists("Address", address_name):
        addr = frappe.get_doc("Address", address_name)
        branch_title = addr.address_title or addr.address_line1 or address_name
        address_line1 = addr.address_line1 or ""
        city = addr.city or ""
        phone = addr.phone or ""
        qr_text = f"MUBTKIR_BRANCH::{customer}::{address_name}"
    else:
        qr_text = f"MUBTKIR_CUSTOMER::{customer}"

    qr_image = generate_branch_qr_data_url(qr_text)
    card_url = get_customer_card_url(customer, address_name)

    from pos_next.api.voucher import get_balance_value, get_balance_expiry_info
    from pos_next.api.whatsapp_hook import get_recipient_mobile

    voucher_balance = cint(get_balance_value(customer, branch=address_name))
    expiry_info = get_balance_expiry_info(customer, branch=address_name)
    mobile_no = get_recipient_mobile(customer, branch_address=address_name)

    has_voucher_activity = voucher_balance > 0
    if not has_voucher_activity and frappe.db.exists("DocType", "Prepaid Voucher Transaction"):
        txn_filters = {"customer": customer}
        if address_name and frappe.db.has_column("Prepaid Voucher Transaction", "branch"):
            txn_filters["branch"] = address_name
        has_voucher_activity = bool(frappe.db.exists("Prepaid Voucher Transaction", txn_filters))

    import urllib.parse
    token = generate_customer_card_token(customer, address_name)
    path_params = {"customer": customer or "", "token": token}
    if address_name:
        path_params["branch"] = address_name
    card_path = f"/customer-card?{urllib.parse.urlencode(path_params)}"

    return {
        "company_name": company_name,
        "customer": customer,
        "customer_name": customer_name,
        "address_name": address_name or "",
        "branch_title": branch_title,
        "address_line1": address_line1,
        "city": city,
        "phone": phone,
        "mobile_no": mobile_no or "",
        "voucher_balance": voucher_balance,
        "has_voucher_activity": has_voucher_activity,
        "expiry_date": expiry_info.get("expiry_date"),
        "days_remaining": expiry_info.get("days_remaining"),
        "qr_data": qr_text,
        "qr_image": qr_image,
        "card_url": card_url,
        "card_path": card_path,
    }


@frappe.whitelist()
def send_customer_qr_whatsapp(customer, address_name=None, mobile_no=None):
    """Send customer's digital voucher & QR card URL via WhatsApp."""
    data = get_customer_qr_card_data(customer, address_name)
    recipient = (mobile_no or data.get("mobile_no") or "").strip()

    if not recipient:
        frappe.throw(
            _("No mobile number found for this customer/branch. Please update the mobile number first."),
            title=_("Missing Mobile Number"),
        )

    company_line = f"*{data['company_name']}*\n" if data.get("company_name") else ""
    branch_line = f"🏢 الفرع: {data['branch_title']}\n" if data.get("branch_title") else ""
    balance_line = f"🎟️ رصيد القسائم المتاح: *{data['voucher_balance']}*\n"

    message = (
        f"{company_line}"
        f"مرحباً {data['customer_name']}،\n"
        f"{branch_line}"
        f"{balance_line}"
        f"📱 يمكنك عرض رمز الـ QR الخاص بك ومتابعة رصيد قسائمك مباشرة عبر الرابط التالي:\n"
        f"{data['card_url']}\n\n"
        f"أبرز هذا الرمز للموظف عند زيارتك لاستخدام رصيدك بسهولة."
    )

    sent = send_whatsapp(recipient, message)
    if not sent:
        frappe.throw(
            _("Could not send WhatsApp message. Please verify WhatsApp integration settings."),
            title=_("WhatsApp Failed"),
        )

    return {
        "sent": True,
        "mobile_no": recipient,
        "card_url": data["card_url"],
    }



