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
    """Validate and return coupon details.

    ``lock=True`` must be used immediately before submission. It places a row
    lock on the coupon so usage limits remain correct under concurrent sales.
    The submitted invoice/order count is the source of truth; the ``used``
    field is a denormalized display counter and is synchronized separately.
    """
    res = {"coupon": None, "valid": False}
    code = _normalize_coupon_code(coupon_code)

    if not code:
        res["msg"] = _("Please enter a coupon code")
        return res

    if lock:
        coupon_name = _lock_coupon_row(code)
    else:
        coupon_name = frappe.db.get_value("POS Coupon", {"coupon_code": code}, "name")

    if not coupon_name:
        res["msg"] = _("Sorry, this coupon code does not exist")
        return res

    coupon = frappe.get_doc("POS Coupon", coupon_name)

    # Check if coupon is disabled
    if coupon.disabled:
        res["msg"] = _("Sorry, this coupon has been disabled")
        return res

    # Check validity dates
    current_date = getdate(today())
    if coupon.valid_from and getdate(coupon.valid_from) > current_date:
        res["msg"] = _("Sorry, this coupon code's validity has not started")
        return res

    if coupon.valid_upto and getdate(coupon.valid_upto) < current_date:
        res["msg"] = _("Sorry, this coupon code has expired")
        return res

    # Company is always validated on a POS transaction. If a caller supplied a
    # company, never allow a cross-company coupon.
    if company and coupon.company != company:
        res["msg"] = _("Sorry, this coupon is not valid for this company")
        return res

    # Check customer restriction (Gift Cards always require their owner; a
    # promotional coupon may also optionally be restricted to one customer).
    if coupon.customer and (not customer or coupon.customer != customer):
        res["msg"] = _("Sorry, this coupon is not valid for this customer")
        return res

    actual_used = _get_coupon_usage_count(code)

    # Usage limits use the actual submitted documents, not a client-controlled
    # field and not a potentially stale counter.
    if coupon.coupon_type == "Gift Card" and actual_used >= 1:
        res["msg"] = _("Sorry, this gift card has already been used")
        return res

    if coupon.maximum_use and actual_used >= int(coupon.maximum_use):
        res["msg"] = _("Sorry, this coupon code has been fully redeemed")
        return res

    # Check one-time use per customer using submitted transactions.
    if coupon.one_use and customer:
        used_count = _get_customer_coupon_usage_count(customer, code)
        if used_count > 0:
            res["msg"] = _("Sorry, you have already used this coupon code")
            return res

    res["coupon"] = coupon
    res["valid"] = True
    res["used"] = actual_used
    return res


def apply_coupon_discount(coupon, cart_total, net_total=None):
    """Calculate authoritative discount amount based on coupon configuration."""
    grand_total = max(flt(cart_total), 0)
    net_amount = max(flt(net_total if net_total is not None else cart_total), 0)

    # Determine the base amount for discount calculation.
    base_amount = grand_total if coupon.apply_on == "Grand Total" else net_amount

    # Check minimum amount
    if coupon.min_amount and flt(base_amount) < flt(coupon.min_amount):
        return {
            "valid": False,
            "message": _("Minimum cart amount of {0} is required").format(
                frappe.format_value(coupon.min_amount, {"fieldtype": "Currency"})
            ),
            "discount": 0,
            "base_amount": base_amount,
        }

    # Calculate discount
    discount = 0
    if coupon.discount_type == "Percentage":
        discount = flt(base_amount) * flt(coupon.discount_percentage) / 100
    elif coupon.discount_type == "Amount":
        discount = flt(coupon.discount_amount)

    # Apply maximum discount limit if configured.
    if coupon.max_amount and flt(discount) > flt(coupon.max_amount):
        discount = flt(coupon.max_amount)

    # Ensure discount cannot make the selected base negative.
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
