# -*- coding: utf-8 -*-
# Copyright (c) 2025, BrainWise and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import json
import frappe
from frappe import _
from frappe.utils import flt, cint, nowdate, nowtime, get_datetime, cstr
from erpnext.stock.doctype.batch.batch import get_batch_qty, get_batch_no
from pos_next.api.security import (
    require_pos_profile_access,
    require_shift_access,
    require_pos_document_access,
)
from pos_next.api.payment_security import (
    resolve_pos_payment_account,
    validate_and_pin_invoice_payments,
)

try:
    from erpnext.accounts.doctype.pricing_rule.pricing_rule import (
        apply_pricing_rule as erpnext_apply_pricing_rule,
    )
    from erpnext.accounts.doctype.pricing_rule.utils import (
        get_applied_pricing_rules as erpnext_get_applied_pricing_rules,
    )
except Exception:  # pragma: no cover - ERPNext not installed in some environments
    erpnext_apply_pricing_rule = None
    erpnext_get_applied_pricing_rules = None


# ==========================================
# Helper Functions
# ==========================================


_ALLOWED_POS_TRANSACTION_DOCTYPES = {"Sales Invoice", "Sales Order"}


def _authorize_pos_transaction(data, existing_doc=None, require_open_shift=True, allow_submitted_existing=False):
    """Authorize a POS invoice/order against profile, company and cashier shift.

    POS cashiers may intentionally have narrower Desk permissions. This function
    is the application-level boundary that must run before any bounded
    ``ignore_permissions`` write in this module.
    """
    data = data or {}
    doctype = data.get("doctype") or (existing_doc.doctype if existing_doc else "Sales Invoice")
    if doctype not in _ALLOWED_POS_TRANSACTION_DOCTYPES:
        frappe.throw(_("Document type {0} is not allowed from POS.").format(doctype), frappe.PermissionError)

    pos_profile = data.get("pos_profile") or (existing_doc.get("pos_profile") if existing_doc else None)
    company = data.get("company") or (existing_doc.get("company") if existing_doc else None)
    profile = require_pos_profile_access(pos_profile, company=company)

    if existing_doc:
        if existing_doc.doctype != doctype:
            frappe.throw(_("Document type cannot be changed."), frappe.PermissionError)
        if existing_doc.docstatus != 0 and not allow_submitted_existing:
            frappe.throw(_("Only draft documents can be updated from POS."), frappe.PermissionError)
        if existing_doc.get("pos_profile") and existing_doc.pos_profile != profile.name:
            frappe.throw(_("This document belongs to another POS Profile."), frappe.PermissionError)
        if existing_doc.get("company") and existing_doc.company != profile.company:
            frappe.throw(_("This document belongs to another company."), frappe.PermissionError)

    shift_name = (
        data.get("posa_pos_opening_shift")
        or (existing_doc.get("posa_pos_opening_shift") if existing_doc else None)
    )
    shift = require_shift_access(
        shift_name,
        pos_profile=profile.name,
        company=profile.company,
        require_open=require_open_shift,
    )

    if existing_doc and existing_doc.get("posa_pos_opening_shift") and existing_doc.posa_pos_opening_shift != shift.name:
        frappe.throw(_("This document belongs to another POS Opening Shift."), frappe.PermissionError)

    return doctype, profile, shift


def _save_authorized_pos_doc(doc):
    """Save after POS authorization while containing the permission bypass."""
    previous_ignore = getattr(frappe.flags, "ignore_account_permission", False)
    frappe.flags.ignore_account_permission = True
    doc.flags.ignore_permissions = True
    try:
        return doc.save(ignore_permissions=True)
    finally:
        frappe.flags.ignore_account_permission = previous_ignore
        doc.flags.ignore_permissions = False


def get_payment_account(mode_of_payment, company, pos_profile=None):
    """Return the server-authoritative payment account.

    In POS context a profile is required to enforce that the payment method is
    configured for that profile and that its company account is valid. The old
    company-only fallback is kept only for internal compatibility outside POS.
    """
    if pos_profile:
        details = resolve_pos_payment_account(
            pos_profile,
            mode_of_payment,
            company=company,
            allow_wallet=False,
        )
        return {"account": details.account}

    # Non-POS compatibility path: use only the explicit company mapping. Do not
    # guess another company account because that can silently post to the wrong GL.
    account = frappe.db.get_value(
        "Mode of Payment Account",
        {"parent": mode_of_payment, "company": company},
        "default_account",
    )
    if account:
        return {"account": account}

    frappe.throw(
        _(
            "Please configure a default account for Mode of Payment {0} in company {1}."
        ).format(mode_of_payment, company),
        title=_("Missing Account"),
    )



# ==========================================
# Discount / Coupon Security Helpers
# ==========================================


def _get_pos_discount_settings(pos_profile):
    """Return server-side discount policy for a POS Profile."""
    defaults = frappe._dict(
        {
            "enabled": 1,
            "allow_user_to_edit_additional_discount": 0,
            "allow_user_to_edit_item_discount": 1,
            "allow_user_to_edit_rate": 0,
            "max_discount_allowed": 0,
        }
    )

    if not pos_profile:
        return defaults

    row = frappe.db.get_value(
        "POS Settings",
        {"pos_profile": pos_profile},
        [
            "enabled",
            "allow_user_to_edit_additional_discount",
            "allow_user_to_edit_item_discount",
            "allow_user_to_edit_rate",
            "max_discount_allowed",
        ],
        as_dict=True,
    )
    if row:
        defaults.update(row)
        # Match the frontend contract: when POS Settings is disabled, its
        # discount controls do not restrict checkout.
        if not cint(row.get("enabled")):
            defaults.allow_user_to_edit_additional_discount = 1
            defaults.allow_user_to_edit_item_discount = 1
            defaults.allow_user_to_edit_rate = 1
            defaults.max_discount_allowed = 0
    return defaults


def _normalize_pricing_rules(value):
    """Normalize item pricing_rules into a stable list of names."""
    if not value:
        return []
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        if raw.startswith("["):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [cstr(v).strip() for v in parsed if cstr(v).strip()]
            except Exception:
                pass
        return [part.strip() for part in raw.split(",") if part.strip()]
    if isinstance(value, (list, tuple, set)):
        return [cstr(v).strip() for v in value if cstr(v).strip()]
    return [cstr(value).strip()] if cstr(value).strip() else []


def _get_authoritative_item_price(item, profile):
    """Fetch the same price-list rate POSNext exposes to the cashier.

    This is intentionally used only for discounted lines so checkout does not
    add a per-item pricing query to every normal sale.
    """
    try:
        from pos_next.api.items import get_item_detail

        item_code = item.get("item_code")
        if not item_code:
            return frappe._dict({"price_list_rate": 0, "max_discount": 0})

        item_master = frappe.get_cached_value(
            "Item",
            item_code,
            ["has_batch_no", "has_serial_no", "is_stock_item"],
            as_dict=True,
        ) or {}

        details = get_item_detail(
            {
                "item_code": item_code,
                "has_batch_no": item_master.get("has_batch_no", 0),
                "has_serial_no": item_master.get("has_serial_no", 0),
                "is_stock_item": item_master.get("is_stock_item", 0),
                "qty": flt(item.get("qty") or item.get("quantity") or 1),
                "uom": item.get("uom"),
            },
            warehouse=None,
            price_list=profile.get("selling_price_list"),
            company=profile.company,
        )
        return frappe._dict(
            {
                "price_list_rate": flt(
                    details.get("price_list_rate") or details.get("rate") or 0
                ),
                "max_discount": flt(details.get("max_discount") or 0),
            }
        )
    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            "POS Discount Price Validation Error",
        )
        return frappe._dict({"price_list_rate": 0, "max_discount": 0})


def _validate_and_normalize_requested_discounts(data, profile):
    """Enforce item/additional-discount policy on the server.

    - UI flags are never trusted as authorization.
    - Claimed Pricing Rules must be applicable according to ERPNext.
    - Discounted lines are rebuilt from the server price-list rate where
      available, preventing a forged price_list_rate from amplifying a discount.
    - Coupon invoice-level amounts are ignored here and recalculated later from
      ERPNext totals.
    """
    settings = _get_pos_discount_settings(profile.name)
    items = data.get("items") or []
    coupon_code = cstr(data.get("coupon_code") or "").strip().upper()

    requested_additional = flt(data.get("discount_amount") or 0)
    if requested_additional < 0:
        frappe.throw(_("Additional discount cannot be negative."))

    # A coupon amount is always server-calculated later. Ignore anything the
    # browser supplied for discount_amount / additional_discount_percentage.
    if coupon_code:
        data["coupon_code"] = coupon_code
        data["discount_amount"] = 0
        data["additional_discount_percentage"] = 0
    elif requested_additional > 0 and not cint(
        settings.allow_user_to_edit_additional_discount
    ):
        frappe.throw(
            _("Additional discount is not allowed for this POS Profile."),
            frappe.PermissionError,
        )

    # Evaluate any claimed pricing rules using ERPNext's engine. A crafted rule
    # name must not turn a manual discount into a trusted promotion.
    claimed_rules = set()
    for row in items:
        claimed_rules.update(_normalize_pricing_rules(row.get("pricing_rules")))

    offer_result = {"items": [], "free_items": [], "applied_pricing_rules": []}
    if claimed_rules:
        offer_result = apply_offers(
            {
                "doctype": data.get("doctype") or "Sales Invoice",
                "pos_profile": profile.name,
                "company": profile.company,
                "customer": data.get("customer"),
                "currency": data.get("currency") or profile.get("currency"),
                "items": items,
            },
            selected_offers=sorted(claimed_rules),
        ) or offer_result

    server_items = offer_result.get("items") or []
    applied_rules = set(offer_result.get("applied_pricing_rules") or [])
    free_items = offer_result.get("free_items") or []

    for index, item in enumerate(items):
        qty = flt(item.get("qty") or item.get("quantity") or 0)
        discount_pct = flt(item.get("discount_percentage") or 0)
        discount_amt = flt(item.get("discount_amount") or 0)
        is_free_item = cint(item.get("is_free_item") or 0)
        client_rules = set(_normalize_pricing_rules(item.get("pricing_rules")))

        if discount_pct < 0 or discount_pct > 100:
            frappe.throw(
                _("Discount percentage for item {0} must be between 0 and 100.").format(
                    item.get("item_code")
                )
            )
        if discount_amt < 0:
            frappe.throw(
                _("Discount amount for item {0} cannot be negative.").format(
                    item.get("item_code")
                )
            )

        server_item = server_items[index] if index < len(server_items) else {}

        # Free products are returned separately by ERPNext's pricing engine, so
        # validate them against free_item_data rather than the same item index.
        if is_free_item:
            verified_rules = client_rules & applied_rules
            valid_free = False
            for free in free_items:
                free_rules = set(_normalize_pricing_rules(free.get("pricing_rules")))
                if (
                    free.get("item_code") == item.get("item_code")
                    and bool(verified_rules & free_rules)
                ):
                    valid_free = True
                    break

            if not client_rules or verified_rules != client_rules or not valid_free:
                frappe.throw(
                    _("Free item {0} is not authorized by an active offer.").format(
                        item.get("item_code")
                    )
                )
            item["rate"] = 0
            item["price_list_rate"] = 0
            item["discount_percentage"] = 0
            item["discount_amount"] = 0
            item["pricing_rules"] = ",".join(sorted(verified_rules))
            continue

        server_rules = set(_normalize_pricing_rules(server_item.get("pricing_rules")))
        verified_rules = client_rules & server_rules & applied_rules

        if client_rules and verified_rules != client_rules:
            frappe.throw(
                _("Pricing rule for item {0} is no longer valid. Refresh the cart and try again.").format(
                    item.get("item_code")
                )
            )

        if verified_rules:
            # Replace browser discount values with ERPNext-calculated values.
            discount_pct = flt(server_item.get("discount_percentage") or 0)
            discount_amt = flt(server_item.get("discount_amount") or 0)
            item["discount_percentage"] = discount_pct
            item["discount_amount"] = discount_amt
            item["pricing_rules"] = ",".join(sorted(verified_rules))

            # Fixed-rate Pricing Rules do not expose a discount percentage. The
            # pricing engine returns the authoritative rule rate as the line's
            # price_list_rate in this path; do not trust a browser-supplied rate.
            if discount_pct <= 0 and discount_amt <= 0:
                rule_rate = flt(server_item.get("price_list_rate") or 0)
                if rule_rate > 0:
                    item["price_list_rate"] = rule_rate
                    item["rate"] = rule_rate
        else:
            item["pricing_rules"] = ""
            has_manual_discount = discount_pct > 0 or discount_amt > 0
            if has_manual_discount and not cint(settings.allow_user_to_edit_item_discount):
                frappe.throw(
                    _("Item discount is not allowed for this POS Profile."),
                    frappe.PermissionError,
                )

        has_discount = flt(item.get("discount_percentage") or 0) > 0 or flt(
            item.get("discount_amount") or 0
        ) > 0
        if not has_discount:
            continue

        price_info = _get_authoritative_item_price(item, profile)
        server_price = flt(price_info.price_list_rate)
        base_amount = max(server_price * abs(qty), 0) if server_price > 0 else max(
            flt(item.get("price_list_rate") or item.get("rate") or 0) * abs(qty), 0
        )

        # Normalize amount/percentage from one server-side base.
        normalized_pct = flt(item.get("discount_percentage") or 0)
        normalized_amt = flt(item.get("discount_amount") or 0)
        if normalized_pct > 0 and base_amount > 0:
            normalized_amt = base_amount * normalized_pct / 100
        elif normalized_amt > 0 and base_amount > 0:
            normalized_pct = normalized_amt / base_amount * 100

        if normalized_pct > 100.0001 or normalized_amt > base_amount + 0.01:
            frappe.throw(
                _("Discount for item {0} exceeds the item value.").format(
                    item.get("item_code")
                )
            )

        # Promotional rules are allowed to exceed manual POS limits. Manual
        # discounts must respect both POS Settings and Item.max_discount.
        if not verified_rules:
            limits = []
            pos_limit = flt(settings.max_discount_allowed or 0)
            item_limit = flt(price_info.max_discount or 0)
            if pos_limit > 0:
                limits.append(pos_limit)
            if item_limit > 0:
                limits.append(item_limit)
            if limits and normalized_pct > min(limits) + 0.0001:
                frappe.throw(
                    _("Discount for item {0} exceeds the maximum allowed discount of {1}%.").format(
                        item.get("item_code"), min(limits)
                    )
                )

        item["discount_percentage"] = normalized_pct
        item["discount_amount"] = normalized_amt

        # For a discounted line, use the authoritative list rate when available
        # and derive the effective unit rate instead of trusting the browser.
        if server_price > 0 and abs(qty) > 0:
            item["price_list_rate"] = server_price
            item["rate"] = max((base_amount - normalized_amt) / abs(qty), 0)

    return settings


def _validate_manual_additional_discount(invoice_doc, settings):
    """Validate invoice-level manual discount against ERPNext-calculated subtotal."""
    amount = flt(invoice_doc.get("discount_amount") or 0)
    if amount < 0:
        frappe.throw(_("Additional discount cannot be negative."))
    if amount <= 0:
        return

    if not cint(settings.allow_user_to_edit_additional_discount):
        frappe.throw(
            _("Additional discount is not allowed for this POS Profile."),
            frappe.PermissionError,
        )

    remaining_base = max(flt(invoice_doc.get("net_total") or 0), 0)
    if amount > remaining_base + 0.01:
        frappe.throw(_("Additional discount cannot exceed the invoice net total."))

    # The frontend expresses Max Discount against the cart subtotal before item
    # discounts. Rebuild the same base from server-normalized item rows so a
    # mixed item + invoice discount is evaluated consistently on both sides.
    policy_base = 0.0
    for row in invoice_doc.get("items", []):
        if cint(row.get("is_free_item") or 0):
            continue
        qty = abs(flt(row.get("qty") or 0))
        price = flt(row.get("price_list_rate") or row.get("rate") or 0)
        policy_base += qty * price
    if policy_base <= 0:
        policy_base = remaining_base

    max_discount = flt(settings.max_discount_allowed or 0)
    if max_discount > 0 and policy_base > 0:
        pct = amount / policy_base * 100
        if pct > max_discount + 0.0001:
            frappe.throw(
                _("Additional discount exceeds the maximum allowed discount of {0}%.").format(
                    max_discount
                )
            )


def _apply_coupon_authoritatively(invoice_doc, coupon_code, lock=False):
    """Recalculate a POS Coupon from ERPNext totals and apply it to the document."""
    code = cstr(coupon_code or "").strip().upper()
    if not code:
        return None
    if invoice_doc.get("is_return"):
        frappe.throw(_("Coupons cannot be applied to return invoices."))

    from pos_next.pos_next.doctype.pos_coupon.pos_coupon import (
        apply_coupon_discount,
        check_coupon_code,
    )

    # Remove any browser-provided invoice-level discount before calculating the
    # base on which this coupon is actually allowed to operate.
    invoice_doc.discount_amount = 0
    if invoice_doc.meta.has_field("additional_discount_percentage"):
        invoice_doc.additional_discount_percentage = 0
    invoice_doc.calculate_taxes_and_totals()

    validation = check_coupon_code(
        code,
        customer=invoice_doc.customer,
        company=invoice_doc.company,
        lock=lock,
    )
    if not validation.get("valid"):
        frappe.throw(validation.get("msg") or _("Invalid coupon code"))

    coupon = validation["coupon"]
    result = apply_coupon_discount(
        coupon,
        cart_total=invoice_doc.grand_total,
        net_total=invoice_doc.net_total,
    )
    if not result.get("valid"):
        frappe.throw(result.get("message") or _("Coupon requirements are not met"))

    invoice_doc.coupon_code = coupon.coupon_code
    if invoice_doc.meta.has_field("apply_discount_on"):
        invoice_doc.apply_discount_on = coupon.apply_on or "Grand Total"
    invoice_doc.discount_amount = flt(result.get("discount") or 0)
    if invoice_doc.meta.has_field("additional_discount_percentage"):
        invoice_doc.additional_discount_percentage = 0
    invoice_doc.calculate_taxes_and_totals()
    return coupon

# ==========================================
# Stock Validation Functions
# ==========================================


def _get_available_stock(item):
    """Return available stock qty for an item row."""
    warehouse = item.get("warehouse")
    batch_no = item.get("batch_no")
    item_code = item.get("item_code")

    if not item_code or not warehouse:
        return 0

    if batch_no:
        return get_batch_qty(batch_no, warehouse) or 0

    # Get stock from Bin
    bin_qty = frappe.db.get_value(
        "Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty"
    )
    return flt(bin_qty) or 0


def _collect_stock_errors(items):
    """Return list of items exceeding available stock."""
    errors = []
    for d in items:
        if flt(d.get("qty")) < 0:
            continue

        available = _get_available_stock(d)
        requested = flt(
            d.get("stock_qty")
            or (flt(d.get("qty")) * flt(d.get("conversion_factor") or 1))
        )

        if requested > available:
            errors.append(
                {
                    "item_code": d.get("item_code"),
                    "warehouse": d.get("warehouse"),
                    "requested_qty": requested,
                    "available_qty": available,
                }
            )

    return errors


def _should_block(pos_profile):
    """Check if sale should be blocked for insufficient stock."""
    # First check global ERPNext Stock Settings
    allow_negative = cint(
        frappe.db.get_single_value("Stock Settings", "allow_negative_stock") or 0
    )
    if allow_negative:
        return False

    # Check POS Settings for the specific profile
    if pos_profile:
        # Check if POS Settings allows negative stock
        pos_settings_allow_negative = cint(
            frappe.db.get_value(
                "POS Settings",
                {"pos_profile": pos_profile},
                "allow_negative_stock"
            ) or 0
        )
        if pos_settings_allow_negative:
            return False

        # Try to get custom field (may not exist in vanilla ERPNext)
        block_sale = cint(
            frappe.db.get_value(
                "POS Profile", pos_profile, "posa_block_sale_beyond_available_qty"
            )
            or 1
        )
        return bool(block_sale)

    # Default to blocking if no profile specified
    return True


def _validate_stock_on_invoice(invoice_doc):
    """Validate stock availability before submission."""
    if invoice_doc.doctype == "Sales Invoice" and not cint(
        getattr(invoice_doc, "update_stock", 0)
    ):
        return

    # Collect all stock items to check
    items_to_check = [d.as_dict() for d in invoice_doc.items if d.get("is_stock_item")]

    # Include packed items if present
    if hasattr(invoice_doc, "packed_items"):
        items_to_check.extend([d.as_dict() for d in invoice_doc.packed_items])

    # Check for stock errors
    errors = _collect_stock_errors(items_to_check)

    # Throw error if stock insufficient and blocking is enabled
    if errors and _should_block(invoice_doc.pos_profile):
        frappe.throw(frappe.as_json({"errors": errors}), frappe.ValidationError)


def _auto_set_return_batches(invoice_doc):
    """Assign batch numbers for return invoices without a source invoice.

    When an item requires a batch number, this function allocates the first
    available batch in FIFO order. If no batches exist in the selected
    warehouse, an informative error is raised.
    """
    if not invoice_doc.get("is_return") or invoice_doc.get("return_against"):
        return

    for d in invoice_doc.items:
        if not d.get("item_code") or not d.get("warehouse"):
            continue

        has_batch = frappe.db.get_value("Item", d.item_code, "has_batch_no")
        if has_batch and not d.get("batch_no"):
            batch_list = (
                get_batch_qty(item_code=d.item_code, warehouse=d.warehouse) or []
            )
            batch_list = [b for b in batch_list if flt(b.get("qty")) > 0]

            if batch_list:
                # FIFO: batches are already sorted by posting/expiry in ERPNext
                d.batch_no = batch_list[0].get("batch_no")
            else:
                frappe.throw(
                    _("No batches available in {0} for {1}.").format(
                        d.warehouse, d.item_code
                    )
                )


# ==========================================
# Validation Functions
# ==========================================


@frappe.whitelist()
def validate_cart_items(items, pos_profile=None):
    """Validate cart items for available stock.

    Returns a list of item dicts where requested quantity exceeds availability.
    This can be used on the front-end for pre-submission checks.
    """
    if isinstance(items, str):
        items = json.loads(items)

    if not pos_profile:
        frappe.throw(_("POS Profile is required."), frappe.PermissionError)
    require_pos_profile_access(pos_profile)

    if not _should_block(pos_profile):
        return []

    errors = _collect_stock_errors(items)
    if not errors:
        return []

    return errors


@frappe.whitelist()
def validate_return_items(original_invoice_name, return_items, doctype="Sales Invoice"):
    """Ensure that return items do not exceed the quantity from the original invoice."""
    if doctype not in _ALLOWED_POS_TRANSACTION_DOCTYPES:
        frappe.throw(_("Document type {0} is not allowed from POS.").format(doctype), frappe.PermissionError)
    require_pos_document_access(doctype, original_invoice_name, ptype="read")
    original_invoice = frappe.get_doc(doctype, original_invoice_name)
    original_item_qty = {}

    for item in original_invoice.items:
        original_item_qty[item.item_code] = (
            original_item_qty.get(item.item_code, 0) + item.qty
        )

    # Get all returned items from this invoice
    returned_items = frappe.get_all(
        doctype,
        filters={
            "return_against": original_invoice_name,
            "docstatus": 1,
            "is_return": 1,
        },
        fields=["name"],
    )

    for returned_invoice in returned_items:
        ret_doc = frappe.get_doc(doctype, returned_invoice.name)
        for item in ret_doc.items:
            if item.item_code in original_item_qty:
                original_item_qty[item.item_code] -= abs(item.qty)

    # Validate new return items
    for item in return_items:
        item_code = item.get("item_code")
        return_qty = abs(item.get("qty", 0))
        if item_code in original_item_qty and return_qty > original_item_qty[item_code]:
            return {
                "valid": False,
                "message": _(
                    "You are trying to return more quantity for item {0} than was sold."
                ).format(item_code),
            }

    return {"valid": True}


# ==========================================
# Invoice Management (Two-Step Flow)
# ==========================================


@frappe.whitelist()
def update_invoice(data):
    """Create or update invoice draft (Step 1)."""
    try:
        data = json.loads(data) if isinstance(data, str) else data

        requested_doctype = data.get("doctype", "Sales Invoice")
        existing_doc = None
        if data.get("name"):
            if not frappe.db.exists(requested_doctype, data.get("name")):
                frappe.throw(_("Document {0} does not exist.").format(data.get("name")))
            existing_doc = frappe.get_doc(requested_doctype, data.get("name"))

        doctype, profile, shift = _authorize_pos_transaction(data, existing_doc=existing_doc)
        pos_profile = profile.name

        # Trust server-side profile/shift context, not client-provided company/user context.
        data["doctype"] = doctype
        data["pos_profile"] = profile.name
        data["company"] = profile.company
        data["posa_pos_opening_shift"] = shift.name

        # Phase 3 / Point 3: discount and coupon policy is enforced server-side
        # before any document is created or updated. This also strips forged
        # pricing-rule metadata and normalizes discounted lines.
        discount_settings = _validate_and_normalize_requested_discounts(data, profile)

        if existing_doc:
            invoice_doc = existing_doc
            invoice_doc.update(data)
        else:
            invoice_doc = frappe.get_doc(data)

        pos_profile_doc = frappe.get_cached_doc("POS Profile", pos_profile)
        invoice_doc.pos_profile = pos_profile
        invoice_doc.company = profile.company
        invoice_doc.posa_pos_opening_shift = shift.name
        if pos_profile_doc.currency and not invoice_doc.get("currency"):
            invoice_doc.currency = pos_profile_doc.currency

        # Copy accounting dimensions from POS Profile
        if hasattr(pos_profile_doc, "branch") and pos_profile_doc.branch:
            invoice_doc.branch = pos_profile_doc.branch
            for item in invoice_doc.get("items", []):
                item.branch = pos_profile_doc.branch

        # Do not resolve payment accounts from caller data at this stage. ERPNext
        # fills normal POS defaults below, then Point 4 revalidates every payment
        # method and pins its account from the authorized POS Profile/company.

        # Validate return items if this is a return invoice
        if (data.get("is_return") or invoice_doc.get("is_return")) and invoice_doc.get(
            "return_against"
        ):
            validation = validate_return_items(
                invoice_doc.return_against,
                [d.as_dict() for d in invoice_doc.items],
                doctype=invoice_doc.doctype,
            )
            if not validation.get("valid"):
                frappe.throw(validation.get("message"))

        # A POS transaction must reference an existing customer. Customer creation
        # is handled by the dedicated customer API with its own permission checks.
        customer_name = invoice_doc.get("customer")
        if customer_name and not frappe.db.exists("Customer", customer_name):
            frappe.throw(_("Customer {0} does not exist. Please create the customer first.").format(customer_name))

        # Disable automatic pricing rules (we handle discounts manually from POS)
        invoice_doc.ignore_pricing_rule = 1
        invoice_doc.flags.ignore_pricing_rule = True

        # ========================================================================
        # DISCOUNT CALCULATION - CRITICAL LOGIC
        # ========================================================================
        # Problem: Frontend sends rate (discounted) and discount_percentage
        # Solution: Reverse-calculate price_list_rate (original price) to avoid double discount
        #
        # Formula: rate = price_list_rate * (1 - discount_percentage/100)
        # Reverse: price_list_rate = rate / (1 - discount_percentage/100)
        # ========================================================================
        for item in invoice_doc.get("items", []):
            item_rate = flt(item.rate or 0)
            discount_pct = flt(item.discount_percentage or 0)

            # If item has a discount, reverse-calculate the original price_list_rate
            if discount_pct > 0 and discount_pct < 100:
                if item_rate > 0:
                    # Reverse calculation to get original price
                    item.price_list_rate = item_rate / (1 - discount_pct / 100)
                elif not item.get("price_list_rate"):
                    # Fallback: if rate is 0 but discount exists (edge case)
                    item.price_list_rate = item_rate
            elif not item.get("price_list_rate"):
                # No discount or price_list_rate not set - use rate as is
                item.price_list_rate = item_rate

            # Ensure price_list_rate is never less than rate (data integrity)
            if flt(item.price_list_rate) < item_rate:
                item.price_list_rate = item_rate

            # IMPORTANT: Keep the rate from frontend (do NOT set to 0)
            # ERPNext will recalculate if needed, but preserving frontend rate
            # prevents rounding issues and ensures UI matches invoice

        # Set invoice flags BEFORE calculations
        if doctype == "Sales Invoice":
            invoice_doc.is_pos = 1
            invoice_doc.update_stock = 1

        # ========================================================================
        # ROUNDING CONFIGURATION
        # ========================================================================
        # Load rounding preference from POS Settings
        # When disabled (0): ERPNext rounds to nearest whole number
        # When enabled (1): Shows exact amount without rounding
        # ========================================================================
        disable_rounded = 1  # Default: disable rounding for POS (show exact amounts)

        if pos_profile:
            try:
                pos_settings_value = frappe.db.get_value(
                    "POS Settings",
                    {"pos_profile": pos_profile},
                    "disable_rounded_total"
                )
                if pos_settings_value is not None:
                    disable_rounded = cint(pos_settings_value)
            except Exception as e:
                # Log error but continue with default
                frappe.log_error(f"Error loading rounding setting: {str(e)}", "POS Invoice Creation")

        invoice_doc.disable_rounded_total = disable_rounded

        # Populate missing fields (company, currency, accounts, etc.)
        # Mute msgprint temporarily: ERPNext's update_multi_mode_option triggers
        # "Payment methods refreshed" msgprint when payments already exist,
        # which the frontend treats as a ValidationError.
        # frappe.throw still works — only informational messages are suppressed.
        frappe.flags.mute_messages = True
        try:
            invoice_doc.set_missing_values()
        finally:
            frappe.flags.mute_messages = False

        # Calculate totals and apply discounts (with rounding disabled)
        invoice_doc.calculate_taxes_and_totals()
        if invoice_doc.grand_total is None:
            invoice_doc.grand_total = 0.0
        if invoice_doc.base_grand_total is None:
            invoice_doc.base_grand_total = 0.0

        # Phase 3 / Point 4: the browser may choose only a payment method
        # configured on this POS Profile. The GL account always comes from the
        # server-side Mode of Payment Account mapping.
        validate_and_pin_invoice_payments(invoice_doc)

        # For return invoices, ensure payments are negative
        if invoice_doc.get("is_return"):
            # Return handling is primarily for Sales Invoice
            if doctype == "Sales Invoice" and invoice_doc.get("payments"):
                for payment in invoice_doc.payments:
                    payment.amount = -abs(payment.amount)
                    if payment.base_amount:
                        payment.base_amount = -abs(payment.base_amount)

                invoice_doc.paid_amount = flt(sum(p.amount for p in invoice_doc.payments))
                invoice_doc.base_paid_amount = flt(
                    sum(p.base_amount or 0 for p in invoice_doc.payments)
                )

        # Coupon discount is always recalculated from ERPNext totals. Manual
        # additional discounts are validated against the POS policy instead.
        coupon_code = data.get("coupon_code")
        if coupon_code:
            if not frappe.db.table_exists("POS Coupon"):
                frappe.throw(_("Coupons are not enabled"))
            _apply_coupon_authoritatively(invoice_doc, coupon_code, lock=False)
        else:
            _validate_manual_additional_discount(invoice_doc, discount_settings)

        # Save as draft. Permission bypass is bounded by _authorize_pos_transaction.
        invoice_doc.docstatus = 0
        _save_authorized_pos_doc(invoice_doc)

        # FIX: Ensure payments from frontend aren't wiped out by custom scripts or ERPNext's set_pos_data.
        # Security: restore in memory first, then re-run wallet validation BEFORE any db_update.
        # This prevents a crafted wallet amount from being persisted after the normal validate hook.
        if data.get("payments"):
            payload_payments_map = {
                p.get("mode_of_payment"): flt(p.get("amount"))
                for p in data.get("payments")
                if p.get("mode_of_payment")
            }
            changed_payments = []

            for p in invoice_doc.payments:
                if p.mode_of_payment in payload_payments_map:
                    payload_amt = payload_payments_map[p.mode_of_payment]
                    if p.amount != payload_amt:
                        p.amount = payload_amt
                        if not p.base_amount or p.base_amount != payload_amt:
                            p.base_amount = payload_amt
                        changed_payments.append(p)

            if changed_payments:
                if doctype == "Sales Invoice":
                    from pos_next.api.wallet import validate_wallet_payment

                    validate_wallet_payment(invoice_doc)

                for p in changed_payments:
                    p.db_update()

                invoice_doc.paid_amount = sum(flt(p.amount) for p in invoice_doc.payments)
                invoice_doc.base_paid_amount = invoice_doc.paid_amount
                invoice_doc.db_update()


        return invoice_doc.as_dict()
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Update Invoice Error")
        raise


def _submit_invoice_response(invoice_doc, offline_id=None, already_synced=False):
    """Return a stable response shape for normal and idempotent submissions."""
    response = {
        "name": invoice_doc.name,
        "status": invoice_doc.docstatus,
        "grand_total": invoice_doc.grand_total,
        "total": invoice_doc.total,
        "net_total": invoice_doc.net_total,
        "outstanding_amount": getattr(invoice_doc, "outstanding_amount", 0),
        "paid_amount": getattr(invoice_doc, "paid_amount", 0),
        "change_amount": getattr(invoice_doc, "change_amount", 0),
    }
    if offline_id:
        response["offline_id"] = offline_id
        response["already_synced"] = bool(already_synced)
    return response


@frappe.whitelist()
def submit_invoice(invoice=None, data=None):
    """Submit the invoice (Step 2)."""
    try:

        # Handle different calling conventions
        if invoice is None:
            if data:
                # Check if data is a JSON string containing both params
                data_parsed = json.loads(data) if isinstance(data, str) else data

                # frappe-ui might send all params nested in data
                if isinstance(data_parsed, dict):
                    if "invoice" in data_parsed:
                        invoice = data_parsed.get("invoice")
                        data = data_parsed.get("data", {})
                    elif "name" in data_parsed or "doctype" in data_parsed:
                        # Data itself might be the invoice
                        invoice = data_parsed
                        data = {}
                    else:
                        frappe.throw(
                            _("Missing invoice parameter. Received data: {0}").format(
                                json.dumps(data_parsed, default=str)
                            )
                        )
                else:
                    frappe.throw(_("Missing invoice parameter"))
            else:
                frappe.throw(_("Both invoice and data parameters are missing"))

        # Parse JSON strings if needed
        if isinstance(data, str):
            data = json.loads(data) if data and data != "{}" else {}
        if isinstance(invoice, str):
            invoice = json.loads(invoice)

        requested_doctype = invoice.get("doctype", "Sales Invoice")

        # Fast idempotent path: if an offline retry arrives after the shift was
        # already closed, we must still be able to return the *already submitted*
        # invoice instead of rejecting the retry or creating another document.
        preflight_offline_id = cstr(
            invoice.get("offline_id") or data.get("offline_id") or ""
        ).strip()
        if preflight_offline_id and requested_doctype == "Sales Invoice":
            from pos_next.pos_next.doctype.offline_invoice_sync.offline_invoice_sync import (
                OfflineInvoiceSync as _OfflineSyncPreflight,
            )

            _state = _OfflineSyncPreflight.get_state(preflight_offline_id)
            _mapped = _state.get("sales_invoice")
            if _mapped and frappe.db.exists("Sales Invoice", _mapped):
                _mapped_doc = frappe.get_doc("Sales Invoice", _mapped)
                if _mapped_doc.docstatus == 1:
                    _authorize_pos_transaction(
                        invoice,
                        existing_doc=_mapped_doc,
                        require_open_shift=False,
                        allow_submitted_existing=True,
                    )
                    _OfflineSyncPreflight.create_sync_record(
                        preflight_offline_id,
                        _mapped_doc.name,
                        pos_profile=_mapped_doc.pos_profile,
                        customer=_mapped_doc.customer,
                        status="Synced",
                    )
                    return _submit_invoice_response(
                        _mapped_doc,
                        offline_id=preflight_offline_id,
                        already_synced=True,
                    )

        existing_for_auth = None
        if invoice.get("name") and frappe.db.exists(requested_doctype, invoice.get("name")):
            existing_for_auth = frappe.get_doc(requested_doctype, invoice.get("name"))

        doctype, profile, shift = _authorize_pos_transaction(invoice, existing_doc=existing_for_auth)
        pos_profile = profile.name
        invoice["doctype"] = doctype
        invoice["pos_profile"] = profile.name
        invoice["company"] = profile.company
        invoice["posa_pos_opening_shift"] = shift.name

        # Re-validate discount policy at submit time. The draft may have been
        # modified after Step 1, and the submit payload itself is untrusted.
        discount_settings = _validate_and_normalize_requested_discounts(invoice, profile)

        offline_id = cstr(invoice.get("offline_id") or data.get("offline_id") or "").strip()
        offline_sync = None

        # Offline invoice idempotency guard. This path is intentionally limited
        # to Sales Invoice so normal Sales Order / online flows are untouched.
        if offline_id and doctype == "Sales Invoice":
            from pos_next.pos_next.doctype.offline_invoice_sync.offline_invoice_sync import (
                OfflineInvoiceSync,
            )

            offline_sync = OfflineInvoiceSync
            sync_state = OfflineInvoiceSync.get_state(offline_id)
            mapped_invoice = sync_state.get("sales_invoice")

            if mapped_invoice and frappe.db.exists("Sales Invoice", mapped_invoice):
                mapped_doc = frappe.get_doc("Sales Invoice", mapped_invoice)
                _authorize_pos_transaction(invoice, existing_doc=mapped_doc, require_open_shift=False, allow_submitted_existing=True)

                # If the first request reached submit but its HTTP response was
                # lost, return that exact invoice instead of creating another.
                if mapped_doc.docstatus == 1:
                    OfflineInvoiceSync.create_sync_record(
                        offline_id,
                        mapped_doc.name,
                        pos_profile=pos_profile,
                        customer=invoice.get("customer"),
                        status="Synced",
                    )
                    return _submit_invoice_response(
                        mapped_doc, offline_id=offline_id, already_synced=True
                    )

                # A previous attempt may have created a draft before failing.
                # Reuse that same draft on retry rather than opening a new one.
                if mapped_doc.docstatus == 0:
                    invoice["name"] = mapped_doc.name

            OfflineInvoiceSync.create_sync_record(
                offline_id,
                invoice.get("name") or "",
                pos_profile=pos_profile,
                customer=invoice.get("customer"),
                status="Pending",
            )

            # offline_id is transport metadata, not a Sales Invoice field.
            invoice = dict(invoice)
            invoice.pop("offline_id", None)

        invoice_name = invoice.get("name")

        # Get or create invoice
        if not invoice_name or not frappe.db.exists(doctype, invoice_name):
            created = update_invoice(json.dumps(invoice))
            invoice_name = created.get("name")
            invoice_doc = frappe.get_doc(doctype, invoice_name)
        else:
            invoice_doc = frappe.get_doc(doctype, invoice_name)
            _authorize_pos_transaction(invoice, existing_doc=invoice_doc)
            invoice_doc.update(invoice)

        if offline_id and offline_sync and doctype == "Sales Invoice":
            offline_sync.create_sync_record(
                offline_id,
                invoice_doc.name,
                pos_profile=pos_profile,
                customer=invoice_doc.customer,
                status="Pending",
            )

        # Ensure update_stock is set for Sales Invoice
        if doctype == "Sales Invoice":
            invoice_doc.update_stock = 1
            invoice_doc.is_pos = 1

        # Copy accounting dimensions from POS Profile if not already set
        if pos_profile and not invoice_doc.get("branch"):
            try:
                pos_profile_doc = frappe.get_cached_doc("POS Profile", pos_profile)
                if hasattr(pos_profile_doc, "branch") and pos_profile_doc.branch:
                    invoice_doc.branch = pos_profile_doc.branch
                    # Also set branch on all items for GL entries
                    for item in invoice_doc.get("items", []):
                        if not item.get("branch"):
                            item.branch = pos_profile_doc.branch
            except Exception:
                pass  # Branch is optional, continue without it

        # Phase 3 / Point 4: re-validate and pin payment accounts immediately
        # before submission so a crafted submit payload cannot swap payment
        # method/account after the draft was created.
        if doctype == "Sales Invoice" and hasattr(invoice_doc, "payments"):
            validate_and_pin_invoice_payments(invoice_doc)

        # Handle sales team (multiple sales persons)
        sales_team_data = invoice.get("sales_team") or data.get("sales_team")
        if sales_team_data:
            # Clear existing sales team entries
            invoice_doc.sales_team = []

            # Add new sales team entries
            for member in sales_team_data:
                invoice_doc.append("sales_team", {
                    "sales_person": member.get("sales_person"),
                    "allocated_percentage": member.get("allocated_percentage", 0),
                })

        # Recalculate coupon discount from current ERPNext totals and lock the
        # coupon row until this transaction completes. This closes the race where
        # two cashiers could consume the last use simultaneously.
        coupon_code = cstr(invoice_doc.get("coupon_code") or "").strip().upper()
        if coupon_code:
            if not frappe.db.table_exists("POS Coupon"):
                frappe.throw(_("Coupons are not enabled"))
            _apply_coupon_authoritatively(invoice_doc, coupon_code, lock=True)
            coupon_code = invoice_doc.coupon_code
        else:
            invoice_doc.calculate_taxes_and_totals()
            _validate_manual_additional_discount(invoice_doc, discount_settings)

        # Auto-set batch numbers for returns
        _auto_set_return_batches(invoice_doc)

        # Check if POS Settings allows negative stock
        pos_settings_allow_negative = False
        if pos_profile:
            pos_settings_allow_negative = cint(
                frappe.db.get_value(
                    "POS Settings",
                    {"pos_profile": pos_profile},
                    "allow_negative_stock"
                ) or 0
            )

        # Validate stock availability only if negative stock is not allowed
        if not pos_settings_allow_negative:
            _validate_stock_on_invoice(invoice_doc)

        # Save before submit. The bounded bypass follows POS profile/shift authorization.
        _save_authorized_pos_doc(invoice_doc)

        # Submit invoice with error handling
        # Note: Negative stock handling is now done through the CustomSalesInvoice override
        # which checks POS Settings in the update_stock_ledger method
        try:
            previous_ignore = getattr(frappe.flags, "ignore_account_permission", False)
            frappe.flags.ignore_account_permission = True
            invoice_doc.flags.ignore_permissions = True
            try:
                invoice_doc.submit()

                # The invoice/order is now submitted while the coupon row lock is
                # still held. Synchronize the usage counter inside the same DB
                # transaction; no manual commit is used.
                if coupon_code:
                    from pos_next.pos_next.doctype.pos_coupon.pos_coupon import (
                        increment_coupon_usage,
                    )

                    increment_coupon_usage(coupon_code, locked=True)
            finally:
                frappe.flags.ignore_account_permission = previous_ignore
                invoice_doc.flags.ignore_permissions = False

            # Record the definitive mapping immediately after successful submit
            # and before building the HTTP response. If the response is lost,
            # the next retry returns this same invoice.
            if offline_id and offline_sync and doctype == "Sales Invoice":
                offline_sync.create_sync_record(
                    offline_id,
                    invoice_doc.name,
                    pos_profile=pos_profile,
                    customer=invoice_doc.customer,
                    status="Synced",
                )
        except Exception as submit_error:
            # If submission fails, cleanup the invoice to prevent stock reservation issues
            try:
                # Reload to get current state
                current_doc = frappe.get_doc(doctype, invoice_doc.name)

                # If already submitted, must cancel before deleting
                if current_doc.docstatus == 1:
                    current_doc.flags.ignore_permissions = True
                    current_doc.cancel()

                # Now delete the cancelled/draft invoice
                frappe.delete_doc(
                    doctype,
                    invoice_doc.name,
                    force=True,
                    ignore_permissions=True,
                )
            except Exception:
                # Silent fail on cleanup - don't hide original error
                pass

            # Re-raise the original submission error
            raise submit_error

        # Handle credit redemption after successful submission
        customer_credit_dict = data.get("customer_credit_dict") or invoice.get("customer_credit_dict")
        redeemed_customer_credit = data.get("redeemed_customer_credit") or invoice.get("redeemed_customer_credit")

        if redeemed_customer_credit and customer_credit_dict:
            try:
                from pos_next.api.credit_sales import redeem_customer_credit
                redeem_customer_credit(invoice_doc.name, customer_credit_dict)
            except Exception as credit_error:
                frappe.log_error(
                    title="Credit Redemption Error",
                    message=f"Invoice: {invoice_doc.name}, Error: {str(credit_error)}\n{frappe.get_traceback()}"
                )
                # Don't fail the entire transaction, just log the error
                frappe.msgprint(
                    _("Invoice submitted successfully but credit redemption failed. Please contact administrator."),
                    alert=True,
                    indicator="orange"
                )

        # Return complete invoice details
        return _submit_invoice_response(invoice_doc, offline_id=offline_id)
    except Exception as e:
        # Preserve the identifier for a safe future retry. Failed attempts are
        # allowed to reuse the same offline_id and, when possible, the same draft.
        try:
            if offline_id and offline_sync:
                state = offline_sync.get_state(offline_id)
                if not state.get("synced"):
                    offline_sync.create_sync_record(
                        offline_id,
                        state.get("sales_invoice") or "",
                        pos_profile=(invoice or {}).get("pos_profile") if isinstance(invoice, dict) else None,
                        customer=(invoice or {}).get("customer") if isinstance(invoice, dict) else None,
                        status="Failed",
                    )
        except Exception:
            pass
        frappe.log_error(frappe.get_traceback(), "Submit Invoice Error")
        raise


# ==========================================
# Invoice History Management
# ==========================================


@frappe.whitelist()
def get_invoice(invoice_name):
	"""
	Get a single invoice with all details for POS.

	Args:
		invoice_name: Sales Invoice name

	Returns:
		Complete invoice document with items and payments
	"""
	if not invoice_name:
		frappe.throw(_("Invoice name is required"))

	if not frappe.db.exists("Sales Invoice", invoice_name):
		frappe.throw(_("Invoice {0} does not exist").format(invoice_name))

	require_pos_document_access("Sales Invoice", invoice_name, ptype="read")

	# Get invoice document
	invoice = frappe.get_doc("Sales Invoice", invoice_name)

	return invoice.as_dict()


def _normalize_phone_sql(expression):
    """Normalize common phone formatting characters for SQL LIKE searches."""
    return (
        f"REPLACE(REPLACE(REPLACE(REPLACE(REPLACE({expression}, '+', ''), ' ', ''), '-', ''), '(', ''), ')', '')"
    )


def _phone_search_value(value):
    """Return a tolerant phone fragment (Saudi local/international formats match)."""
    digits = "".join(ch for ch in cstr(value or "") if ch.isdigit())
    if len(digits) >= 9:
        # Last 9 digits makes 05XXXXXXXX and 9665XXXXXXXX match each other.
        return digits[-9:]
    return digits


def _get_invoice_phone_sql():
    """Return SQL fragments for customer phone without assuming custom fields exist."""
    sales_invoice_meta = frappe.get_meta("Sales Invoice")
    customer_meta = frappe.get_meta("Customer")

    phone_sources = []
    normalized_sources = []

    if sales_invoice_meta.has_field("custom_phone"):
        phone_sources.append("NULLIF(si.custom_phone, '')")
        normalized_sources.append(_normalize_phone_sql("COALESCE(si.custom_phone, '')"))

    if customer_meta.has_field("mobile_no"):
        phone_sources.append("NULLIF(c.mobile_no, '')")
        normalized_sources.append(_normalize_phone_sql("COALESCE(c.mobile_no, '')"))

    phone_expression = "COALESCE(" + ", ".join(phone_sources) + ", '')" if phone_sources else "''"
    return phone_expression, normalized_sources


@frappe.whitelist()
def search_invoices(
    pos_profile=None,
    page=1,
    page_length=30,
    search=None,
    date_from=None,
    date_to=None,
    status=None,
    customer=None,
    customer_phone=None,
    pos_status=None,
    product=None,
    returns=None,
    posa_pos_opening_shift=None,
):
    """
    Lightweight, server-side paginated invoice search for POS.

    - With ``posa_pos_opening_shift`` it is used by Invoice History and returns
      only invoices from the current session.
    - Without a shift it searches all POS invoices for the POS Profile company,
      across sessions and POS profiles. This powers Invoice Management.
    - Invoice items are *not* loaded. Full details are fetched only when a user
      opens an invoice.
    """
    if not pos_profile:
        frappe.throw(_("POS Profile is required"))

    profile = frappe.db.get_value(
        "POS Profile", pos_profile, ["name", "company"], as_dict=True
    )
    if not profile:
        frappe.throw(_("POS Profile {0} does not exist").format(pos_profile))

    # Invoice Management may search all POS invoices for the profile company,
    # but the caller must still be an authorized user of the selected profile.
    require_pos_profile_access(pos_profile, company=profile.company)

    sales_invoice_meta = frappe.get_meta("Sales Invoice")

    page = max(cint(page), 1)
    page_length = min(max(cint(page_length), 1), 100)
    offset = (page - 1) * page_length

    conditions = [
        "si.company = %(company)s",
        "si.docstatus = 1",
        "si.is_pos = 1",
    ]
    params = {
        "company": profile.company,
        "limit": page_length,
        "offset": offset,
    }

    if posa_pos_opening_shift:
        conditions.append("si.posa_pos_opening_shift = %(posa_pos_opening_shift)s")
        params["posa_pos_opening_shift"] = posa_pos_opening_shift

    if returns not in (None, "", "all"):
        return_value = cint(returns)
        conditions.append("si.is_return = %(is_return)s")
        params["is_return"] = 1 if return_value else 0

    if date_from:
        conditions.append("si.posting_date >= %(date_from)s")
        params["date_from"] = date_from
    if date_to:
        conditions.append("si.posting_date <= %(date_to)s")
        params["date_to"] = date_to
    if status:
        conditions.append("si.status = %(status)s")
        params["status"] = status
    if customer:
        params["customer"] = f"%{cstr(customer).strip()}%"
        conditions.append("(si.customer LIKE %(customer)s OR si.customer_name LIKE %(customer)s)")
    if pos_status and sales_invoice_meta.has_field("pos_status"):
        conditions.append("si.pos_status = %(pos_status)s")
        params["pos_status"] = pos_status

    phone_expression, normalized_phone_sources = _get_invoice_phone_sql()
    pos_status_expression = "si.pos_status" if sales_invoice_meta.has_field("pos_status") else "''"

    if customer_phone:
        phone_value = _phone_search_value(customer_phone)
        if phone_value and normalized_phone_sources:
            params["customer_phone"] = f"%{phone_value}%"
            conditions.append(
                "("
                + " OR ".join(
                    f"{source} LIKE %(customer_phone)s" for source in normalized_phone_sources
                )
                + ")"
            )

    if search:
        raw_search = cstr(search).strip()
        params["search"] = f"%{raw_search}%"
        general_search = [
            "si.name LIKE %(search)s",
            "si.customer LIKE %(search)s",
            "si.customer_name LIKE %(search)s",
        ]
        phone_value = _phone_search_value(raw_search)
        if len(phone_value) >= 5 and normalized_phone_sources:
            params["search_phone"] = f"%{phone_value}%"
            general_search.extend(
                f"{source} LIKE %(search_phone)s" for source in normalized_phone_sources
            )
        conditions.append("(" + " OR ".join(general_search) + ")")

    if product:
        params["product"] = f"%{cstr(product).strip()}%"
        conditions.append(
            """EXISTS (
                SELECT 1
                FROM `tabSales Invoice Item` sii
                WHERE sii.parent = si.name
                  AND (sii.item_code LIKE %(product)s OR sii.item_name LIKE %(product)s)
            )"""
        )

    where_clause = " AND ".join(conditions)

    # Count is intentionally separate from the data query; both remain bounded
    # and avoid the previous N+1 item query for every invoice.
    total = frappe.db.sql(
        f"""
        SELECT COUNT(*)
        FROM `tabSales Invoice` si
        LEFT JOIN `tabCustomer` c ON c.name = si.customer
        WHERE {where_clause}
        """,
        params,
    )[0][0]

    invoices = frappe.db.sql(
        f"""
        SELECT
            si.name,
            si.customer,
            si.customer_name,
            {phone_expression} AS custom_phone,
            si.posting_date,
            si.posting_time,
            si.grand_total,
            si.paid_amount,
            si.outstanding_amount,
            si.status,
            {pos_status_expression} AS pos_status,
            si.docstatus,
            si.is_return,
            si.return_against,
            si.pos_profile,
            si.posa_pos_opening_shift
        FROM `tabSales Invoice` si
        LEFT JOIN `tabCustomer` c ON c.name = si.customer
        WHERE {where_clause}
        ORDER BY si.posting_date DESC, si.posting_time DESC, si.creation DESC
        LIMIT %(limit)s OFFSET %(offset)s
        """,
        params,
        as_dict=True,
    )

    return {
        "data": invoices,
        "total": cint(total),
        "page": page,
        "page_length": page_length,
        "has_more": offset + len(invoices) < cint(total),
    }


@frappe.whitelist()
def get_invoices(pos_profile, limit=100, posa_pos_opening_shift=None):
    """Backward-compatible lightweight invoice list.

    The old implementation executed one extra item query per invoice. Keep the
    public API for callers, but delegate to the paginated search path so legacy
    callers no longer trigger N+1 database queries.
    """
    result = search_invoices(
        pos_profile=pos_profile,
        page=1,
        page_length=min(max(cint(limit), 1), 100),
        posa_pos_opening_shift=posa_pos_opening_shift,
    )
    return result.get("data", [])


@frappe.whitelist()
def get_draft_invoices(pos_opening_shift, doctype="Sales Invoice"):
    """Get draft POS documents only for an authorized opening shift."""
    if doctype not in _ALLOWED_POS_TRANSACTION_DOCTYPES:
        frappe.throw(_("Document type {0} is not allowed from POS.").format(doctype), frappe.PermissionError)
    require_shift_access(pos_opening_shift, require_open=False)

    filters = {"docstatus": 0}
    if frappe.db.has_column(doctype, "posa_pos_opening_shift"):
        filters["posa_pos_opening_shift"] = pos_opening_shift
    else:
        # Without a shift link we cannot safely expose arbitrary drafts.
        return []

    invoices_list = frappe.get_all(
        doctype,
        filters=filters,
        fields=["name"],
        limit_page_length=0,
        order_by="modified desc",
    )
    return [frappe.get_cached_doc(doctype, row["name"]) for row in invoices_list]


@frappe.whitelist()
def delete_invoice(invoice):
    """Delete an authorized draft Sales Invoice from the cashier's shift."""
    doctype = "Sales Invoice"
    row = frappe.db.get_value(
        doctype,
        invoice,
        ["name", "docstatus", "pos_profile", "company", "posa_pos_opening_shift"],
        as_dict=True,
    )
    if not row:
        frappe.throw(_("Invoice {0} does not exist").format(invoice))
    if row.docstatus != 0:
        frappe.throw(_("Cannot delete submitted invoice {0}").format(invoice))

    require_pos_profile_access(row.pos_profile, company=row.company)
    require_shift_access(
        row.posa_pos_opening_shift,
        pos_profile=row.pos_profile,
        company=row.company,
        require_open=True,
    )
    frappe.delete_doc(doctype, invoice, force=1, ignore_permissions=True)
    return _("Invoice {0} Deleted").format(invoice)


@frappe.whitelist()
def cleanup_old_drafts(pos_profile=None, max_age_hours=24):
    """Clean old draft invoices owned by the current cashier for one POS Profile."""
    from datetime import datetime, timedelta

    profile = require_pos_profile_access(pos_profile)
    cutoff_time = datetime.now() - timedelta(hours=max(int(max_age_hours), 1))

    # Never let one cashier's background cleanup delete another cashier's drafts.
    shift_names = frappe.get_all(
        "POS Opening Shift",
        filters={
            "user": frappe.session.user,
            "pos_profile": profile.name,
            "company": profile.company,
        },
        pluck="name",
        limit_page_length=0,
    )
    if not shift_names:
        return {"deleted": 0, "message": "Cleaned up 0 old draft invoices"}

    old_drafts = frappe.get_all(
        "Sales Invoice",
        filters={
            "docstatus": 0,
            "pos_profile": profile.name,
            "company": profile.company,
            "posa_pos_opening_shift": ["in", shift_names],
            "modified": ["<", cutoff_time.strftime("%Y-%m-%d %H:%M:%S")],
        },
        fields=["name"],
        limit_page_length=100,
    )

    deleted_count = 0
    for draft in old_drafts:
        try:
            frappe.delete_doc(
                "Sales Invoice", draft["name"], force=True, ignore_permissions=True
            )
            deleted_count += 1
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                "Draft Cleanup Error",
            )

    return {
        "deleted": deleted_count,
        "message": f"Cleaned up {deleted_count} old draft invoices",
    }


# ==========================================
# Return Invoice Management
# ==========================================


@frappe.whitelist()
def get_returnable_invoices(limit=50, pos_profile=None):
    """Get list of invoices that have items available for return."""
    # Performance: Use SQL aggregation to calculate returned quantities in one query.
    profile = require_pos_profile_access(pos_profile)
    limit = max(1, min(cint(limit or 50), 100))

    query = """
        SELECT
            si.name,
            si.customer,
            si.customer_name,
            si.posting_date,
            si.grand_total,
            si.status,
            COALESCE(SUM(CASE WHEN ret_item.qty IS NOT NULL THEN ABS(ret_item.qty) ELSE 0 END), 0) as total_returned_qty,
            COALESCE(SUM(CASE WHEN si_item.qty IS NOT NULL THEN si_item.qty ELSE 0 END), 0) as total_original_qty
        FROM `tabSales Invoice` si
        LEFT JOIN `tabSales Invoice Item` si_item ON si_item.parent = si.name
        LEFT JOIN `tabSales Invoice` ret_si ON ret_si.return_against = si.name
            AND ret_si.docstatus = 1
            AND ret_si.is_return = 1
        LEFT JOIN `tabSales Invoice Item` ret_item ON ret_item.parent = ret_si.name
            AND (ret_item.sales_invoice_item = si_item.name OR ret_item.item_code = si_item.item_code)
        WHERE si.docstatus = 1
            AND si.is_return = 0
            AND si.is_pos = 1
            AND si.company = %s
        GROUP BY si.name
        HAVING total_original_qty > total_returned_qty
        ORDER BY si.posting_date DESC, si.creation DESC
        LIMIT %s
    """

    returnable_invoices = frappe.db.sql(query, [profile.company, limit], as_dict=1)

    return returnable_invoices


@frappe.whitelist()
def get_invoice_for_return(invoice_name, pos_profile=None):
    """Get invoice with return tracking - calculates remaining qty for each item."""
    if not frappe.db.exists("Sales Invoice", invoice_name):
        frappe.throw(_("Invoice {0} does not exist").format(invoice_name))

    # Get the original invoice and authorize it against the current POS company.
    invoice = frappe.get_doc("Sales Invoice", invoice_name)
    if pos_profile:
        profile = require_pos_profile_access(pos_profile)
        if invoice.company != profile.company:
            frappe.throw(_("This invoice belongs to another company."), frappe.PermissionError)
    elif not frappe.has_permission("Sales Invoice", "read", invoice_name):
        frappe.throw(_("You don't have permission to view this invoice."), frappe.PermissionError)

    # Performance: Use SQL aggregation to calculate returned quantities in one query
    # This eliminates N+1 queries by aggregating all return items at once
    returned_qty_query = """
        SELECT
            COALESCE(ret_item.sales_invoice_item, ret_item.item_code) as key_field,
            SUM(ABS(ret_item.qty)) as returned_qty
        FROM `tabSales Invoice` ret_si
        INNER JOIN `tabSales Invoice Item` ret_item ON ret_item.parent = ret_si.name
        WHERE ret_si.return_against = %s
            AND ret_si.docstatus = 1
            AND ret_si.is_return = 1
        GROUP BY key_field
    """

    returned_qty_results = frappe.db.sql(returned_qty_query, [invoice_name], as_dict=1)
    returned_qty = {row["key_field"]: row["returned_qty"] for row in returned_qty_results}

    # Calculate remaining quantities
    invoice_dict = invoice.as_dict()
    updated_items = []

    for item in invoice_dict.get("items", []):
        # Check how much has been returned using the item's name (row ID)
        already_returned = returned_qty.get(item.name, 0)
        remaining_qty = item.qty - already_returned

        if remaining_qty > 0:
            item_copy = item.copy()
            item_copy["original_qty"] = item.qty
            item_copy["qty"] = remaining_qty
            item_copy["already_returned"] = already_returned
            updated_items.append(item_copy)

    invoice_dict["items"] = updated_items
    return invoice_dict


@frappe.whitelist()
def prepare_return_invoice(invoice_name, pos_opening_shift=None):
    """Prepare a return invoice using ERPNext's make_sales_return.

    This uses ERPNext's standard return document creation which properly copies
    all child tables including:
    - sales_team: For correct commission reversal on returned items
    - taxes: For correct tax reversal
    - Other child tables maintained by ERPNext

    The function validates:
    - Invoice exists and is submitted (docstatus = 1)
    - Invoice is not already a return
    - Return is within the validity period (if configured in POS Settings)

    Args:
        invoice_name: The original Sales Invoice name to create return against
        pos_opening_shift: The current POS Opening Shift name

    Returns:
        dict: The prepared return invoice document with:
            - items: Only items with remaining_qty > 0 (not fully returned)
            - _original_invoice: Reference data from original invoice (payments, amounts)
            - Each item includes original_qty, already_returned, and remaining_qty
    """
    from frappe.utils import date_diff, getdate
    from frappe.query_builder.functions import Sum, Abs, Coalesce
    from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return

    # Validate invoice and get fields needed for return period check
    si = frappe.qb.DocType("Sales Invoice")
    invoice_check = (
        frappe.qb.from_(si)
        .select(
            si.docstatus,
            si.is_return,
            si.pos_profile,
            si.company,
            si.posting_date,
            si.is_pos,
            si.grand_total,
            si.paid_amount,
            si.outstanding_amount
        )
        .where(si.name == invoice_name)
    ).run(as_dict=True)

    if not invoice_check:
        frappe.throw(_("Invoice {0} does not exist").format(invoice_name))

    invoice_info = invoice_check[0]

    if not pos_opening_shift:
        frappe.throw(_("An open POS shift is required to create a return."), frappe.PermissionError)
    current_shift = require_shift_access(pos_opening_shift, require_open=True)
    if invoice_info.company != current_shift.company:
        frappe.throw(_("This invoice belongs to another company."), frappe.PermissionError)

    # Validate docstatus
    if invoice_info.docstatus != 1:
        frappe.throw(_("Invoice must be submitted to create a return"))

    # Check if it's already a return
    if invoice_info.is_return:
        frappe.throw(_("Cannot create return against a return invoice"))

    # Check return validity period from POS Settings
    if invoice_info.pos_profile:
        return_validity_days = cint(
            frappe.db.get_value(
                "POS Settings",
                {"pos_profile": invoice_info.pos_profile},
                "return_validity_days"
            ) or 0
        )

        if return_validity_days > 0:
            from frappe.utils import nowdate
            days_since_invoice = date_diff(getdate(nowdate()), getdate(invoice_info.posting_date))
            if days_since_invoice > return_validity_days:
                frappe.throw(
                    _("Return period has expired. Invoice {0} was created {1} days ago. "
                      "Returns are only allowed within {2} days of purchase.").format(
                        invoice_name, days_since_invoice, return_validity_days
                    )
                )

    # Use ERPNext's make_sales_return to create properly mapped return document
    # This automatically copies sales_team, taxes, and other child tables
    return_doc = make_sales_return(invoice_name)

    # Set POS-specific fields from the authenticated current shift.
    return_doc.posa_pos_opening_shift = current_shift.name
    return_doc.is_pos = invoice_info.is_pos
    return_doc.pos_profile = current_shift.pos_profile
    return_doc.company = current_shift.company

    # Aggregate quantities already returned from previous return invoices
    ret_si = frappe.qb.DocType("Sales Invoice")
    ret_item = frappe.qb.DocType("Sales Invoice Item")

    returned_qty_results = (
        frappe.qb.from_(ret_si)
        .inner_join(ret_item).on(ret_item.parent == ret_si.name)
        .select(
            Coalesce(ret_item.sales_invoice_item, ret_item.item_code).as_("key_field"),
            Sum(Abs(ret_item.qty)).as_("returned_qty")
        )
        .where(
            (ret_si.return_against == invoice_name)
            & (ret_si.docstatus == 1)
            & (ret_si.is_return == 1)
        )
        .groupby(Coalesce(ret_item.sales_invoice_item, ret_item.item_code))
    ).run(as_dict=True)

    returned_qty_map = {row["key_field"]: flt(row["returned_qty"]) for row in returned_qty_results}

    # Convert to dict and update items with remaining quantities
    return_dict = return_doc.as_dict()

    # Fetch original invoice payments for refund handling in frontend
    si_payment = frappe.qb.DocType("Sales Invoice Payment")
    payments_data = (
        frappe.qb.from_(si_payment)
        .select(
            si_payment.mode_of_payment,
            si_payment.amount,
            si_payment.base_amount,
            si_payment.account
        )
        .where(si_payment.parent == invoice_name)
    ).run(as_dict=True)

    # Include original invoice data for reference (payments, amounts, etc.)
    return_dict["_original_invoice"] = {
        "name": invoice_name,
        "grand_total": invoice_info.grand_total,
        "paid_amount": invoice_info.paid_amount,
        "outstanding_amount": invoice_info.outstanding_amount,
        "payments": payments_data,
    }

    updated_items = []
    for item in return_dict.get("items", []):
        # Get the original item reference (sales_invoice_item points to original item name)
        original_item_ref = item.get("sales_invoice_item") or item.get("item_code")
        already_returned = returned_qty_map.get(original_item_ref, 0)

        # The qty from make_sales_return is already negative (full original qty negated)
        # We need to calculate remaining returnable qty
        original_qty = abs(flt(item.get("qty", 0)))
        remaining_qty = original_qty - already_returned

        if remaining_qty > 0:
            item_copy = item.copy()
            # Store quantities for frontend use
            item_copy["original_qty"] = original_qty
            item_copy["already_returned"] = already_returned
            item_copy["remaining_qty"] = remaining_qty
            # Set qty to negative of remaining (for return)
            item_copy["qty"] = -remaining_qty
            updated_items.append(item_copy)

    return_dict["items"] = updated_items

    # Check if all items have been fully returned
    if not updated_items:
        frappe.throw(_("All items from this invoice have already been returned"))

    return return_dict


@frappe.whitelist()
def search_invoices_for_return(
    invoice_name=None,
    company=None,
    pos_profile=None,
    customer_name=None,
    customer_id=None,
    mobile_no=None,
    from_date=None,
    to_date=None,
    min_amount=None,
    max_amount=None,
    page=1,
    doctype="Sales Invoice",
):
    """Search for returnable invoices within an authorized POS company."""
    if doctype != "Sales Invoice":
        frappe.throw(_("Only Sales Invoice can be searched for returns."), frappe.PermissionError)

    if pos_profile:
        profile = require_pos_profile_access(pos_profile, company=company)
        company = profile.company
    elif company:
        # Non-POS callers must rely on normal Sales Invoice read permissions.
        if not frappe.has_permission("Sales Invoice", "read"):
            frappe.throw(_("You don't have permission to view sales invoices."), frappe.PermissionError)
    else:
        frappe.throw(_("POS Profile or company is required."), frappe.PermissionError)

    # Start with base filters
    filters = {
        "docstatus": 1,
        "is_return": 0,
    }

    if company:
        filters["company"] = company

    # Convert page to integer
    if page and isinstance(page, str):
        page = int(page)
    else:
        page = 1

    # Items per page
    page_length = 100
    start = (page - 1) * page_length

    # Add invoice name filter
    if invoice_name:
        filters["name"] = ["like", f"%{invoice_name}%"]

    # Add date range filters
    if from_date:
        filters["posting_date"] = [">=", from_date]

    if to_date:
        if "posting_date" in filters:
            filters["posting_date"] = ["between", [from_date, to_date]]
        else:
            filters["posting_date"] = ["<=", to_date]

    # Add amount filters
    if min_amount:
        filters["grand_total"] = [">=", float(min_amount)]

    if max_amount:
        if "grand_total" in filters:
            filters["grand_total"] = ["between", [float(min_amount), float(max_amount)]]
        else:
            filters["grand_total"] = ["<=", float(max_amount)]

    # If any customer search criteria is provided, find matching customers
    customer_ids = []
    if customer_name or customer_id or mobile_no:
        conditions = []
        params = {}

        if customer_name:
            conditions.append("customer_name LIKE %(customer_name)s")
            params["customer_name"] = f"%{customer_name}%"

        if customer_id:
            conditions.append("name LIKE %(customer_id)s")
            params["customer_id"] = f"%{customer_id}%"

        if mobile_no:
            conditions.append("mobile_no LIKE %(mobile_no)s")
            params["mobile_no"] = f"%{mobile_no}%"

        where_clause = " OR ".join(conditions)
        customer_query = f"""
			SELECT name
			FROM `tabCustomer`
			WHERE {where_clause}
			LIMIT 100
		"""

        customers = frappe.db.sql(customer_query, params, as_dict=True)
        customer_ids = [c.name for c in customers]

        if customer_ids:
            filters["customer"] = ["in", customer_ids]
        elif any([customer_name, customer_id, mobile_no]):
            return {"invoices": [], "has_more": False}

    # Count total invoices
    total_count_query = frappe.get_list(
        doctype,
        filters=filters,
        fields=["count(name) as total_count"],
        as_list=False,
    )
    total_count = total_count_query[0].total_count if total_count_query else 0

    # Get invoices with pagination
    invoices_list = frappe.get_list(
        doctype,
        filters=filters,
        fields=["name"],
        limit_start=start,
        limit_page_length=page_length,
        order_by="posting_date desc, name desc",
    )

    if not invoices_list:
        return {"invoices": [], "has_more": False}

    # Performance: Batch query all returned quantities for all invoices at once
    # This eliminates N+1 queries by aggregating return data in a single SQL call
    invoice_names = [inv["name"] for inv in invoices_list]

    returned_qty_query = """
        SELECT
            ret_si.return_against as invoice_name,
            ret_item.item_code,
            SUM(ABS(ret_item.qty)) as returned_qty
        FROM `tabSales Invoice` ret_si
        INNER JOIN `tabSales Invoice Item` ret_item ON ret_item.parent = ret_si.name
        WHERE ret_si.return_against IN %s
            AND ret_si.docstatus = 1
            AND ret_si.is_return = 1
        GROUP BY ret_si.return_against, ret_item.item_code
    """

    returned_qty_results = frappe.db.sql(returned_qty_query, [invoice_names], as_dict=1)

    # Build a map of invoice_name -> {item_code: returned_qty}
    returned_qty_map = {}
    for row in returned_qty_results:
        inv_name = row["invoice_name"]
        if inv_name not in returned_qty_map:
            returned_qty_map[inv_name] = {}
        returned_qty_map[inv_name][row["item_code"]] = row["returned_qty"]

    # Process and return results
    data = []

    for invoice in invoices_list:
        invoice_doc = frappe.get_doc(doctype, invoice.name)
        returned_qty = returned_qty_map.get(invoice.name, {})

        if returned_qty:
            # Filter items with remaining qty
            filtered_items = []
            for item in invoice_doc.items:
                already_returned = returned_qty.get(item.item_code, 0)
                remaining_qty = item.qty - already_returned

                if remaining_qty > 0:
                    new_item = item.as_dict().copy()
                    new_item["qty"] = remaining_qty
                    new_item["amount"] = remaining_qty * item.rate
                    if item.get("stock_qty"):
                        new_item["stock_qty"] = (
                            item.stock_qty / item.qty * remaining_qty
                            if item.qty
                            else remaining_qty
                        )
                    filtered_items.append(frappe._dict(new_item))

            if filtered_items:
                filtered_invoice = frappe.get_doc(doctype, invoice.name)
                filtered_invoice.items = filtered_items
                data.append(filtered_invoice)
        else:
            data.append(invoice_doc)

    # Check if there are more results
    has_more = (start + page_length) < total_count

    return {"invoices": data, "has_more": has_more}


# ==========================================
# Legacy/Helper Functions
# ==========================================


@frappe.whitelist()
def apply_offers(invoice_data, selected_offers=None):
    """Calculate and apply promotional offers using ERPNext Pricing Rules.

    Args:
            invoice_data (str | dict): Sales Invoice payload used for offer evaluation.
            selected_offers (str | list | None): Optional collection of Pricing Rule names.
                    When provided, results are filtered to only include these rules.
                    ERPNext handles all conflict resolution based on priority.
    """
    try:
        if isinstance(invoice_data, str):
            invoice_data = json.loads(invoice_data or "{}")

        invoice = frappe._dict(invoice_data or {})
        items = invoice.get("items") or []

        if isinstance(selected_offers, str):
            try:
                selected_offers = json.loads(selected_offers)
            except ValueError:
                selected_offers = [selected_offers]

        if isinstance(selected_offers, (list, tuple, set)):
            selected_offer_names = {
                cstr(name) for name in selected_offers if cstr(name)
            }
        else:
            selected_offer_names = set()

        if not items:
            return {"items": []}

        if not invoice.get("pos_profile") or not erpnext_apply_pricing_rule:
            # Either no POS profile supplied or ERPNext promotional engine unavailable
            return {"items": items}

        require_pos_profile_access(invoice.get("pos_profile"))
        profile = frappe.get_doc("POS Profile", invoice.get("pos_profile"))

        pricing_items = []
        index_map = []
        prepared_items = [frappe._dict(row) for row in items]

        for idx, item in enumerate(prepared_items):
            item_code = item.get("item_code")
            qty = flt(item.get("qty") or item.get("quantity") or 0)

            if not item_code or qty <= 0:
                continue

            try:
                cached = frappe.get_cached_value(
                    "Item",
                    item_code,
                    ["item_name", "item_group", "brand", "stock_uom"],
                    as_dict=1,
                )
            except frappe.DoesNotExistError:
                cached = None

            conversion_factor = flt(item.get("conversion_factor") or 1) or 1
            price_list_rate = flt(item.get("price_list_rate") or item.get("rate") or 0)

            pricing_items.append(
                frappe._dict(
                    {
                        "doctype": "Sales Invoice Item",
                        "name": item.get("name") or f"POS-{idx}",
                        "item_code": item_code,
                        "item_name": (
                            cached.item_name if cached else item.get("item_name")
                        ),
                        "item_group": (
                            cached.item_group if cached else item.get("item_group")
                        ),
                        "brand": (cached.brand if cached else item.get("brand")),
                        "qty": qty,
                        "stock_qty": qty * conversion_factor,
                        "conversion_factor": conversion_factor,
                        "uom": item.get("uom")
                        or item.get("stock_uom")
                        or (cached.stock_uom if cached else None),
                        "stock_uom": item.get("stock_uom")
                        or (cached.stock_uom if cached else None),
                        "price_list_rate": price_list_rate,
                        "base_price_list_rate": price_list_rate,
                        "rate": flt(item.get("rate") or price_list_rate),
                        "base_rate": flt(item.get("rate") or price_list_rate),
                        "discount_percentage": 0,
                        "discount_amount": 0,
                        "warehouse": item.get("warehouse") or profile.warehouse,
                        "parenttype": invoice.get("doctype") or "Sales Invoice",
                    }
                )
            )
            index_map.append(idx)

            # Clear previously applied promotional metadata if the
            # current quantity can no longer satisfy the rule.
            item.discount_percentage = 0
            item.discount_amount = 0
            item.pricing_rules = []
            item.applied_promotional_schemes = []

        if not pricing_items:
            return {"items": items}

        company_currency = frappe.get_cached_value(
            "Company", profile.company, "default_currency"
        )

        # Get customer details if customer is provided
        customer = invoice.get("customer")
        customer_group = invoice.get("customer_group")
        territory = invoice.get("territory")

        if customer and not customer_group:
            # Fetch customer_group from customer
            try:
                customer_data = frappe.get_cached_value(
                    "Customer", customer, ["customer_group", "territory"], as_dict=1
                )
                if customer_data:
                    customer_group = customer_data.get("customer_group")
                    if not territory:
                        territory = customer_data.get("territory")
            except Exception:
                pass

        # If still no customer_group, use default
        if not customer_group:
            customer_group = "All Customer Groups"

        pricing_args = frappe._dict(
            {
                "doctype": invoice.get("doctype") or "Sales Invoice",
                "name": invoice.get("name") or "POS-INVOICE",
                "company": profile.company,
                "transaction_date": invoice.get("posting_date") or nowdate(),
                "posting_date": invoice.get("posting_date") or nowdate(),
                "currency": invoice.get("currency")
                or profile.get("currency")
                or company_currency,
                "conversion_rate": flt(invoice.get("conversion_rate") or 1) or 1,
                "plc_conversion_rate": flt(invoice.get("plc_conversion_rate") or 1)
                or 1,
                "price_list": invoice.get("price_list")
                or profile.get("selling_price_list"),
                "customer": customer,
                "customer_group": customer_group,
                "territory": territory,
                "items": pricing_items,
            }
        )

        # Call ERPNext pricing engine - it handles all conflicts based on priority
        pricing_results = erpnext_apply_pricing_rule(pricing_args) or []

        if not pricing_results:
            return {"items": items}

        raw_rule_names = set()
        for result in pricing_results:
            if not result:
                continue
            rules = []
            if erpnext_get_applied_pricing_rules:
                rules = erpnext_get_applied_pricing_rules(result.get("pricing_rules"))
            else:
                raw_rules = result.get("pricing_rules") or []
                if isinstance(raw_rules, str):
                    if raw_rules.startswith("["):
                        rules = json.loads(raw_rules)
                    else:
                        rules = [r.strip() for r in raw_rules.split(",") if r.strip()]
                elif isinstance(raw_rules, (list, tuple, set)):
                    rules = list(raw_rules)
            raw_rule_names.update(rules)

        rule_map = {}
        if raw_rule_names:
            rule_records = frappe.get_all(
                "Pricing Rule",
                filters={"name": ["in", list(raw_rule_names)]},
                fields=[
                    "name",
                    "promotional_scheme",
                    "coupon_code_based",
                    "promotional_scheme_id",
                    "price_or_product_discount",
                ],
            )
            for record in rule_records:
                # Any active non-coupon Pricing Rule returned by ERPNext may be
                # validated here, including standalone rules. Coupon-based rules
                # are handled separately by the POS Coupon flow.
                if not record.coupon_code_based:
                    rule_map[record.name] = record

        if selected_offer_names:
            # Restrict available rules to the ones explicitly selected from the UI.
            rule_map = {
                name: details
                for name, details in rule_map.items()
                if name in selected_offer_names
            }

        if not rule_map:
            return {"items": items}

        applied_rules = set()
        free_items = []

        for result, item_index in zip(pricing_results, index_map):
            if not result:
                continue

            if erpnext_get_applied_pricing_rules:
                rule_names = erpnext_get_applied_pricing_rules(
                    result.get("pricing_rules")
                )
            else:
                raw_rules = result.get("pricing_rules") or []
                if isinstance(raw_rules, str):
                    if raw_rules.startswith("["):
                        rule_names = json.loads(raw_rules)
                    else:
                        rule_names = [
                            r.strip() for r in raw_rules.split(",") if r.strip()
                        ]
                elif isinstance(raw_rules, (list, tuple, set)):
                    rule_names = list(raw_rules)
                else:
                    rule_names = []

            applicable_rule_names = [
                name for name in rule_names or [] if name in rule_map
            ]

            if not applicable_rule_names:
                continue

            applied_rules.update(applicable_rule_names)

            item_doc = prepared_items[item_index]
            qty = flt(item_doc.get("qty") or item_doc.get("quantity") or 0)
            price_list_rate = flt(
                result.get("price_list_rate")
                or item_doc.get("price_list_rate")
                or item_doc.get("rate")
                or 0
            )

            # Get discount from result or fetch from pricing rule
            discount_percentage = flt(result.get("discount_percentage") or 0)
            per_unit_discount = flt(result.get("discount_amount") or 0)

            # If ERPNext didn't calculate discount (validate_applied_rule=1),
            # we need to fetch and apply it manually
            if (
                not discount_percentage
                and not per_unit_discount
                and applicable_rule_names
            ):
                for rule_name in applicable_rule_names:
                    rule_doc = rule_map.get(rule_name)
                    if not rule_doc:
                        continue

                    # Fetch full pricing rule to get discount values
                    full_rule = frappe.get_cached_doc("Pricing Rule", rule_name)

                    if (
                        full_rule.rate_or_discount == "Discount Percentage"
                        and full_rule.discount_percentage
                    ):
                        discount_percentage += flt(full_rule.discount_percentage)
                    elif (
                        full_rule.rate_or_discount == "Discount Amount"
                        and full_rule.discount_amount
                    ):
                        per_unit_discount += flt(full_rule.discount_amount)
                    elif full_rule.rate_or_discount == "Rate" and full_rule.rate:
                        # Apply fixed rate
                        price_list_rate = flt(full_rule.rate)

            line_discount_amount = 0
            if discount_percentage and qty and price_list_rate:
                line_discount_amount = price_list_rate * qty * discount_percentage / 100
            elif per_unit_discount and qty:
                line_discount_amount = per_unit_discount * qty
            else:
                line_discount_amount = per_unit_discount

            if (
                not discount_percentage
                and line_discount_amount
                and qty
                and price_list_rate
            ):
                base_amount = price_list_rate * qty
                if base_amount:
                    discount_percentage = (line_discount_amount / base_amount) * 100

            item_doc.discount_percentage = discount_percentage
            item_doc.discount_amount = line_discount_amount
            item_doc.price_list_rate = price_list_rate
            item_doc.rate = flt(item_doc.get("rate") or price_list_rate)
            item_doc.pricing_rules = applicable_rule_names

            item_doc.applied_promotional_schemes = list(
                {
                    rule_map[name].promotional_scheme
                    for name in applicable_rule_names
                    if rule_map[name].promotional_scheme
                }
            )

            for free_item in result.get("free_item_data") or []:
                rule_name = free_item.get("pricing_rules")
                if not rule_name or rule_name not in rule_map:
                    continue
                free_item_doc = frappe._dict(free_item)
                free_item_doc.applied_promotional_scheme = rule_map[
                    rule_name
                ].promotional_scheme
                free_items.append(free_item_doc)

        return {
            "items": [dict(item) for item in prepared_items],
            "free_items": [dict(item) for item in free_items],
            "applied_pricing_rules": sorted(applied_rules),
        }
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Apply Offers Error")
        frappe.throw(_("Error applying offers: {0}").format(str(e)))
