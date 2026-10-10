# Copyright (c) 2021, Youssef Restom and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, strip, today


# Submitted sales documents that consume a POS Coupon.
# Sales Order is included because POSNext can submit orders directly and the
# customer has already received the commercial discount at that point.
COUPON_USAGE_DOCTYPES = ("Sales Invoice", "POS Invoice", "Sales Order")


class POSCoupon(Document):
    def autoname(self):
        self.coupon_name = strip(self.coupon_name)
        self.name = self.coupon_name

        if not self.coupon_code:
            if self.coupon_type == "Promotional":
                self.coupon_code = "".join(i for i in self.coupon_name if not i.isdigit())[0:8].upper()
            elif self.coupon_type == "Gift Card":
                self.coupon_code = frappe.generate_hash()[:10].upper()

    def validate(self):
        if self.coupon_code:
            self.coupon_code = _normalize_coupon_code(self.coupon_code)

        # Gift Card validations
        if self.coupon_type == "Gift Card":
            self.maximum_use = 1
            if not self.customer:
                frappe.throw(_("Please select the customer for Gift Card."))

        # Discount validations
        if not self.discount_type:
            frappe.throw(_("Discount Type is required"))

        if self.discount_type == "Percentage":
            if not self.discount_percentage:
                frappe.throw(_("Discount Percentage is required"))
            if flt(self.discount_percentage) <= 0 or flt(self.discount_percentage) > 100:
                frappe.throw(_("Discount Percentage must be between 0 and 100"))
        elif self.discount_type == "Amount":
            if not self.discount_amount:
                frappe.throw(_("Discount Amount is required"))
            if flt(self.discount_amount) <= 0:
                frappe.throw(_("Discount Amount must be greater than 0"))

        # Minimum amount validation
        if self.min_amount and flt(self.min_amount) < 0:
            frappe.throw(_("Minimum Amount cannot be negative"))

        # Maximum discount validation
        if self.max_amount and flt(self.max_amount) <= 0:
            frappe.throw(_("Maximum Discount Amount must be greater than 0"))

        # Date validations
        if self.valid_from and self.valid_upto:
            if getdate(self.valid_from) > getdate(self.valid_upto):
                frappe.throw(_("Valid From date cannot be after Valid Until date"))


def _normalize_coupon_code(coupon_code):
    return (coupon_code or "").strip().upper()


def _get_erpnext_coupon_name(coupon_code):
    """Resolve an entered code to the canonical ERPNext Coupon Code document name.

    ERPNext stores the human-entered coupon in ``coupon_code`` while transaction
    documents store a Link to the Coupon Code document ``name``. POS users type
    the code, so we must resolve it before saving the invoice.
    """
    raw = (coupon_code or "").strip()
    code = _normalize_coupon_code(raw)
    if not code or not frappe.db.table_exists("Coupon Code"):
        return None

    name = frappe.db.get_value("Coupon Code", {"coupon_code": raw}, "name")
    if not name and raw != code:
        name = frappe.db.get_value("Coupon Code", {"coupon_code": code}, "name")
    if name:
        return name

    # Also accept the canonical document name for submit/retry flows. Preserve
    # its original case instead of uppercasing a Link value.
    if raw and frappe.db.exists("Coupon Code", raw):
        return raw

    return None


def _lock_erpnext_coupon_row(coupon_code):
    """Lock the canonical ERPNext coupon row until the current transaction ends."""
    name = _get_erpnext_coupon_name(coupon_code)
    if not name:
        return None

    table = frappe.qb.DocType("Coupon Code")
    rows = (
        frappe.qb.from_(table)
        .select(table.name)
        .where(table.name == name)
        .for_update()
        .run()
    )
    return rows[0][0] if rows else None


def _get_erpnext_pricing_rule(coupon):
    if not coupon or coupon.doctype != "Coupon Code" or not coupon.get("pricing_rule"):
        return None
    if not frappe.db.exists("Pricing Rule", coupon.pricing_rule):
        return None
    return frappe.get_cached_doc("Pricing Rule", coupon.pricing_rule)


def _validate_erpnext_coupon(coupon, customer=None, company=None):
    """Validate ERPNext's native Coupon Code without trusting browser data."""
    current_date = getdate(today())

    if coupon.valid_from and getdate(coupon.valid_from) > current_date:
        return _("Sorry, this coupon code's validity has not started")
    if coupon.valid_upto and getdate(coupon.valid_upto) < current_date:
        return _("Sorry, this coupon code has expired")
    if coupon.maximum_use and int(coupon.used or 0) >= int(coupon.maximum_use):
        return _("Sorry, this coupon code has been fully redeemed")
    if coupon.coupon_type == "Gift Card" and coupon.customer and coupon.customer != customer:
        return _("Sorry, this coupon is not valid for this customer")

    rule = _get_erpnext_pricing_rule(coupon)
    if not rule:
        return _("This coupon is not linked to a valid Pricing Rule")
    if rule.disable:
        return _("The Pricing Rule linked to this coupon is disabled")
    if not rule.selling:
        return _("The Pricing Rule linked to this coupon is not enabled for selling")
    if company and rule.company and rule.company != company:
        return _("Sorry, this coupon is not valid for this company")
    if rule.valid_from and getdate(rule.valid_from) > current_date:
        return _("The Pricing Rule linked to this coupon is not active yet")
    if rule.valid_upto and getdate(rule.valid_upto) < current_date:
        return _("The Pricing Rule linked to this coupon has expired")

    return None


def _lock_coupon_row(coupon_code):
    """Lock one coupon row for the rest of the current DB transaction.

    This serializes concurrent checkout requests using the same coupon so two
    requests cannot both pass a maximum-use / one-use check at the same time.
    """
    code = _normalize_coupon_code(coupon_code)
    if not code:
        return None

    rows = frappe.db.sql(
        """
        SELECT name
        FROM `tabPOS Coupon`
        WHERE coupon_code = %s
        FOR UPDATE
        """,
        (code,),
        as_dict=True,
    )
    return rows[0].name if rows else None


def _get_coupon_usage_count(coupon_code):
    """Return authoritative submitted usage count across POS sales doctypes."""
    code = _normalize_coupon_code(coupon_code)
    if not code:
        return 0

    used_count = 0
    for doctype in COUPON_USAGE_DOCTYPES:
        if not frappe.db.table_exists(doctype):
            continue

        meta = frappe.get_meta(doctype)
        if not meta.has_field("coupon_code"):
            continue

        used_count += frappe.db.count(
            doctype,
            filters={"coupon_code": code, "docstatus": 1},
        )

    return used_count


def _get_customer_coupon_usage_count(customer, coupon_code):
    """Count submitted coupon usage for one customer."""
    code = _normalize_coupon_code(coupon_code)
    if not customer or not code:
        return 0

    used_count = 0
    for doctype in COUPON_USAGE_DOCTYPES:
        if not frappe.db.table_exists(doctype):
            continue

        meta = frappe.get_meta(doctype)
        if not meta.has_field("coupon_code") or not meta.has_field("customer"):
            continue

        used_count += frappe.db.count(
            doctype,
            filters={
                "customer": customer,
                "coupon_code": code,
                "docstatus": 1,
            },
        )

    return used_count


def check_coupon_code(coupon_code, customer=None, company=None, lock=False):
    """Validate a coupon, preferring ERPNext's native Coupon Code.

    Priority is intentional: if the same entered code exists in both ERPNext
    ``Coupon Code`` and the legacy ``POS Coupon`` doctype, ERPNext is the source
    of truth. This removes the need to duplicate coupons inside POSNext.
    """
    res = {"coupon": None, "valid": False, "source": None}
    code = _normalize_coupon_code(coupon_code)

    if not code:
        res["msg"] = _("Please enter a coupon code")
        return res

    # 1) Native ERPNext Coupon Code is the primary source.
    erp_coupon_name = (
        _lock_erpnext_coupon_row(coupon_code)
        if lock
        else _get_erpnext_coupon_name(coupon_code)
    )
    if erp_coupon_name:
        coupon = frappe.get_doc("Coupon Code", erp_coupon_name)
        error = _validate_erpnext_coupon(coupon, customer=customer, company=company)
        if error:
            res["msg"] = error
            return res

        res.update(
            {
                "coupon": coupon,
                "pricing_rule": _get_erpnext_pricing_rule(coupon),
                "valid": True,
                "source": "ERPNext",
                "used": int(coupon.used or 0),
                "entered_code": code,
            }
        )
        return res

    # 2) Legacy POS Coupon remains supported as a fallback.
    if not frappe.db.table_exists("POS Coupon"):
        res["msg"] = _("Sorry, this coupon code does not exist")
        return res

    if lock:
        coupon_name = _lock_coupon_row(code)
    else:
        coupon_name = frappe.db.get_value("POS Coupon", {"coupon_code": code}, "name")

    if not coupon_name:
        res["msg"] = _("Sorry, this coupon code does not exist")
        return res

    coupon = frappe.get_doc("POS Coupon", coupon_name)

    if coupon.disabled:
        res["msg"] = _("Sorry, this coupon has been disabled")
        return res

    current_date = getdate(today())
    if coupon.valid_from and getdate(coupon.valid_from) > current_date:
        res["msg"] = _("Sorry, this coupon code's validity has not started")
        return res
    if coupon.valid_upto and getdate(coupon.valid_upto) < current_date:
        res["msg"] = _("Sorry, this coupon code has expired")
        return res
    if company and coupon.company != company:
        res["msg"] = _("Sorry, this coupon is not valid for this company")
        return res
    if coupon.customer and (not customer or coupon.customer != customer):
        res["msg"] = _("Sorry, this coupon is not valid for this customer")
        return res

    actual_used = _get_coupon_usage_count(code)
    if coupon.coupon_type == "Gift Card" and actual_used >= 1:
        res["msg"] = _("Sorry, this gift card has already been used")
        return res
    if coupon.maximum_use and actual_used >= int(coupon.maximum_use):
        res["msg"] = _("Sorry, this coupon code has been fully redeemed")
        return res
    if coupon.one_use and customer:
        used_count = _get_customer_coupon_usage_count(customer, code)
        if used_count > 0:
            res["msg"] = _("Sorry, you have already used this coupon code")
            return res

    res.update(
        {
            "coupon": coupon,
            "valid": True,
            "source": "POS",
            "used": actual_used,
            "entered_code": code,
        }
    )
    return res


def apply_coupon_discount(coupon, cart_total, net_total=None, pricing_rule=None):
    """Calculate the authoritative preview/checkout discount.

    Native ERPNext coupons derive their discount from the linked Pricing Rule.
    Legacy POS Coupons keep using their own discount fields.
    """
    grand_total = max(flt(cart_total), 0)
    net_amount = max(flt(net_total if net_total is not None else cart_total), 0)

    if getattr(coupon, "doctype", None) == "Coupon Code":
        rule = pricing_rule or _get_erpnext_pricing_rule(coupon)
        if not rule:
            return {"valid": False, "message": _("This coupon is not linked to a valid Pricing Rule"), "discount": 0}

        # POSNext currently represents coupons in the cart as an invoice-level
        # discount. Native transaction Pricing Rules map exactly to that model.
        # Item/product rules remain handled by ERPNext when the document is
        # validated; here we return a safe preview rather than inventing values.
        if rule.apply_on != "Transaction":
            return {
                "valid": True,
                "discount": 0,
                "base_amount": net_amount,
                "discount_type": "Pricing Rule",
                "discount_percentage": 0,
                "apply_on": rule.apply_on,
                "pricing_rule": rule.name,
                "requires_pricing_rule_engine": True,
            }

        eligibility_amount = net_amount
        if rule.min_amt and eligibility_amount < flt(rule.min_amt):
            return {
                "valid": False,
                "message": _("Minimum cart amount of {0} is required").format(
                    frappe.format_value(rule.min_amt, {"fieldtype": "Currency"})
                ),
                "discount": 0,
                "base_amount": eligibility_amount,
            }
        if rule.max_amt and eligibility_amount > flt(rule.max_amt):
            return {
                "valid": False,
                "message": _("This coupon is only valid up to a cart amount of {0}").format(
                    frappe.format_value(rule.max_amt, {"fieldtype": "Currency"})
                ),
                "discount": 0,
                "base_amount": eligibility_amount,
            }

        apply_on = rule.apply_discount_on or "Grand Total"
        base_amount = grand_total if apply_on == "Grand Total" else net_amount
        discount = 0
        discount_type = "Percentage"
        percentage = 0

        if rule.price_or_product_discount == "Price":
            if rule.rate_or_discount == "Discount Percentage":
                percentage = flt(rule.discount_percentage)
                discount = base_amount * percentage / 100
            elif rule.rate_or_discount == "Discount Amount":
                discount_type = "Amount"
                discount = flt(rule.discount_amount)
            elif rule.rate_or_discount == "Rate":
                return {
                    "valid": False,
                    "message": _("Transaction coupons using a fixed Rate are not supported in POS."),
                    "discount": 0,
                }
        else:
            return {
                "valid": True,
                "discount": 0,
                "base_amount": base_amount,
                "discount_type": "Product",
                "discount_percentage": 0,
                "apply_on": apply_on,
                "pricing_rule": rule.name,
                "requires_pricing_rule_engine": True,
            }

        discount = max(min(flt(discount), flt(base_amount)), 0)
        return {
            "valid": True,
            "discount": discount,
            "base_amount": base_amount,
            "discount_type": discount_type,
            "discount_percentage": percentage,
            "apply_on": apply_on,
            "pricing_rule": rule.name,
            "source": "ERPNext",
        }

    # Legacy POS Coupon
    base_amount = grand_total if coupon.apply_on == "Grand Total" else net_amount
    if coupon.min_amount and flt(base_amount) < flt(coupon.min_amount):
        return {
            "valid": False,
            "message": _("Minimum cart amount of {0} is required").format(
                frappe.format_value(coupon.min_amount, {"fieldtype": "Currency"})
            ),
            "discount": 0,
            "base_amount": base_amount,
        }

    discount = 0
    if coupon.discount_type == "Percentage":
        discount = flt(base_amount) * flt(coupon.discount_percentage) / 100
    elif coupon.discount_type == "Amount":
        discount = flt(coupon.discount_amount)
    if coupon.max_amount and flt(discount) > flt(coupon.max_amount):
        discount = flt(coupon.max_amount)
    discount = max(min(flt(discount), flt(base_amount)), 0)

    return {
        "valid": True,
        "discount": discount,
        "base_amount": base_amount,
        "discount_type": coupon.discount_type,
        "discount_percentage": (
            coupon.discount_percentage if coupon.discount_type == "Percentage" else None
        ),
        "apply_on": coupon.apply_on,
        "source": "POS",
    }



def evaluate_erpnext_item_coupon(
    coupon,
    pricing_rule,
    items,
    *,
    company,
    customer=None,
    pos_profile=None,
    currency=None,
    price_list=None,
    posting_date=None,
):
    """Evaluate an item/group/brand ERPNext coupon using ERPNext's own engine.

    Only updates produced by the coupon's linked Pricing Rule are returned. This
    lets POSNext support native item coupons without enabling every unrelated
    automatic Pricing Rule on the transaction.
    """
    if not pricing_rule or pricing_rule.apply_on == "Transaction":
        return {"valid": False, "message": _("Item coupon evaluation is not required")}

    try:
        from erpnext.accounts.doctype.pricing_rule.pricing_rule import apply_pricing_rule
        from erpnext.accounts.doctype.pricing_rule.utils import get_applied_pricing_rules
    except Exception:
        return {"valid": False, "message": _("ERPNext Pricing Rule engine is unavailable")}

    raw_items = items or []
    if isinstance(raw_items, str):
        raw_items = frappe.parse_json(raw_items) or []
    if not raw_items:
        return {"valid": False, "message": _("Add at least one item before applying this coupon")}

    profile = frappe.get_cached_doc("POS Profile", pos_profile) if pos_profile else None
    company_currency = frappe.get_cached_value("Company", company, "default_currency")
    txn_currency = currency or (profile.get("currency") if profile else None) or company_currency
    selling_price_list = price_list or (profile.get("selling_price_list") if profile else None)

    customer_group = None
    territory = None
    if customer:
        customer_data = frappe.get_cached_value(
            "Customer", customer, ["customer_group", "territory"], as_dict=1
        )
        if customer_data:
            customer_group = customer_data.get("customer_group")
            territory = customer_data.get("territory")

    pricing_items = []
    index_map = []
    original_items = [frappe._dict(row) for row in raw_items]
    for idx, row in enumerate(original_items):
        item_code = row.get("item_code")
        qty = flt(row.get("qty") or row.get("quantity") or 0)
        if not item_code or qty <= 0:
            continue

        item_master = frappe.get_cached_value(
            "Item", item_code, ["item_name", "item_group", "brand", "stock_uom"], as_dict=1
        ) or frappe._dict()
        conversion_factor = flt(row.get("conversion_factor") or 1) or 1
        price_list_rate = flt(row.get("price_list_rate") or row.get("rate") or 0)
        pricing_items.append(
            frappe._dict(
                {
                    "doctype": "Sales Invoice Item",
                    "name": row.get("name") or f"POS-COUPON-{idx}",
                    "item_code": item_code,
                    "item_name": item_master.get("item_name") or row.get("item_name"),
                    "item_group": item_master.get("item_group") or row.get("item_group"),
                    "brand": item_master.get("brand") or row.get("brand"),
                    "qty": qty,
                    "stock_qty": qty * conversion_factor,
                    "conversion_factor": conversion_factor,
                    "uom": row.get("uom") or row.get("stock_uom") or item_master.get("stock_uom"),
                    "stock_uom": row.get("stock_uom") or item_master.get("stock_uom"),
                    "price_list_rate": price_list_rate,
                    "base_price_list_rate": price_list_rate,
                    "rate": flt(row.get("rate") or price_list_rate),
                    "base_rate": flt(row.get("rate") or price_list_rate),
                    "discount_percentage": 0,
                    "discount_amount": 0,
                    "warehouse": row.get("warehouse") or (profile.get("warehouse") if profile else None),
                    "parenttype": "Sales Invoice",
                }
            )
        )
        index_map.append(idx)

    if not pricing_items:
        return {"valid": False, "message": _("No eligible items were found for this coupon")}

    pricing_args = frappe._dict(
        {
            "doctype": "Sales Invoice",
            "name": "POS-COUPON-PREVIEW",
            "company": company,
            "transaction_date": posting_date or today(),
            "posting_date": posting_date or today(),
            "currency": txn_currency,
            "conversion_rate": 1,
            "plc_conversion_rate": 1,
            "price_list": selling_price_list,
            "customer": customer,
            "customer_group": customer_group,
            "territory": territory,
            "coupon_code": coupon.name,
            "items": pricing_items,
        }
    )

    results = apply_pricing_rule(pricing_args) or []
    updates = []
    free_items = []
    total_discount = 0.0
    linked_rule = pricing_rule.name

    for result, item_index in zip(results, index_map):
        if not result:
            continue
        rule_names = get_applied_pricing_rules(result.get("pricing_rules")) or []
        if linked_rule not in rule_names:
            continue

        original = original_items[item_index]
        qty = flt(original.get("qty") or original.get("quantity") or 0)
        original_price = flt(original.get("price_list_rate") or original.get("rate") or 0)
        price_list_rate = flt(result.get("price_list_rate") or original_price)
        discount_percentage = flt(result.get("discount_percentage") or 0)
        discount_amount = flt(result.get("discount_amount") or 0)

        # validate_applied_rule can intentionally omit calculated values; use the
        # linked rule's configured value in that case, matching ERPNext behavior.
        if not discount_percentage and not discount_amount:
            if pricing_rule.rate_or_discount == "Discount Percentage":
                discount_percentage = flt(pricing_rule.discount_percentage)
                discount_amount = price_list_rate * discount_percentage / 100
            elif pricing_rule.rate_or_discount == "Discount Amount":
                discount_amount = flt(pricing_rule.discount_amount)
            elif pricing_rule.rate_or_discount == "Rate":
                price_list_rate = flt(result.get("price_list_rate") or pricing_rule.rate or price_list_rate)

        if pricing_rule.rate_or_discount == "Rate":
            final_rate = price_list_rate
            line_discount = max((original_price - final_rate) * qty, 0)
            discount_percentage = (
                (line_discount / (original_price * qty)) * 100
                if original_price and qty
                else 0
            )
            discount_amount = max(original_price - final_rate, 0)
        else:
            final_rate = max(price_list_rate - discount_amount, 0)
            if discount_percentage:
                final_rate = max(price_list_rate * (1 - discount_percentage / 100), 0)
            line_discount = max((price_list_rate - final_rate) * qty, 0)

        total_discount += line_discount
        updates.append(
            {
                "index": item_index,
                "item_code": original.get("item_code"),
                "price_list_rate": price_list_rate,
                "rate": final_rate,
                "discount_percentage": discount_percentage,
                "discount_amount": discount_amount,
                "pricing_rule": linked_rule,
            }
        )

        for free_item in result.get("free_item_data") or []:
            if free_item.get("pricing_rules") == linked_rule:
                free_items.append(dict(free_item))

    if not updates and not free_items:
        return {
            "valid": False,
            "message": _("This coupon is not applicable to the current cart"),
            "discount": 0,
        }

    return {
        "valid": True,
        "discount": total_discount,
        "base_amount": sum(
            flt(row.get("price_list_rate") or row.get("rate") or 0)
            * flt(row.get("qty") or row.get("quantity") or 0)
            for row in original_items
        ),
        "discount_type": "Pricing Rule",
        "discount_percentage": 0,
        "apply_on": pricing_rule.apply_on,
        "pricing_rule": linked_rule,
        "item_updates": updates,
        "free_items": free_items,
        "source": "ERPNext",
    }


def sync_coupon_usage_counter(coupon_code, locked=False):
    """Synchronize the denormalized ``used`` field with submitted documents."""
    code = _normalize_coupon_code(coupon_code)
    if not code:
        return 0

    coupon_name = None
    if locked:
        coupon_name = frappe.db.get_value("POS Coupon", {"coupon_code": code}, "name")
    else:
        coupon_name = _lock_coupon_row(code)

    if not coupon_name:
        return 0

    actual_used = _get_coupon_usage_count(code)
    frappe.db.set_value(
        "POS Coupon",
        coupon_name,
        "used",
        actual_used,
        update_modified=False,
    )
    return actual_used


def increment_coupon_usage(coupon_code, locked=False):
    """Synchronize usage after a successful submitted transaction.

    Kept under the legacy function name for compatibility. No manual commit is
    performed; the counter participates in the invoice transaction atomically.
    """
    return sync_coupon_usage_counter(coupon_code, locked=locked)


def decrement_coupon_usage(coupon_code):
    """Synchronize usage after a submitted transaction is cancelled."""
    return sync_coupon_usage_counter(coupon_code, locked=False)
