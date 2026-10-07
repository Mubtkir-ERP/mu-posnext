"""POSNext request authorization helpers.

These helpers provide an application-level authorization boundary for POS API
endpoints that intentionally need to perform ERPNext writes on behalf of a
cashier who might not have broad Desk permissions.  The important rule is that
``ignore_permissions`` is only used *after* the current session has been
validated against the POS Profile / opening shift / company involved.
"""

from __future__ import unicode_literals

import frappe
from frappe import _
from frappe.utils import cint


def _require_authenticated():
    user = frappe.session.user
    if not user or user == "Guest":
        frappe.throw(_("Authentication is required."), frappe.PermissionError)
    if not cint(frappe.db.get_value("User", user, "enabled") or 0):
        frappe.throw(_("Your user account is disabled."), frappe.PermissionError)
    return user


def _is_privileged_pos_admin(user=None):
    user = user or frappe.session.user
    if user == "Administrator":
        return True
    try:
        return "System Manager" in frappe.get_roles(user)
    except Exception:
        return False


def user_has_pos_profile_access(pos_profile, user=None):
    """Return whether ``user`` is allowed to operate the POS Profile."""
    user = user or _require_authenticated()
    if _is_privileged_pos_admin(user):
        return True
    return bool(
        frappe.db.exists(
            "POS Profile User",
            {"parent": pos_profile, "parenttype": "POS Profile", "user": user},
        )
    )


def require_pos_profile_access(pos_profile, company=None, user=None):
    """Validate an enabled POS Profile, its company and the current cashier."""
    user = user or _require_authenticated()
    if not pos_profile:
        frappe.throw(_("POS Profile is required."), frappe.ValidationError)

    profile = frappe.db.get_value(
        "POS Profile",
        pos_profile,
        ["name", "company", "disabled", "currency", "warehouse"],
        as_dict=True,
    )
    if not profile:
        frappe.throw(_("POS Profile {0} does not exist.").format(pos_profile))
    if cint(profile.disabled):
        frappe.throw(_("POS Profile {0} is disabled.").format(pos_profile))
    if company and profile.company != company:
        frappe.throw(
            _("POS Profile {0} belongs to company {1}, not {2}.").format(
                pos_profile, profile.company, company
            ),
            frappe.PermissionError,
        )
    if not user_has_pos_profile_access(pos_profile, user=user):
        frappe.throw(
            _("You don't have access to POS Profile {0}.").format(pos_profile),
            frappe.PermissionError,
        )
    return profile


def require_company_access(company, user=None):
    """Require access to at least one enabled POS Profile for ``company``."""
    user = user or _require_authenticated()
    if not company:
        frappe.throw(_("Company is required."), frappe.ValidationError)
    if _is_privileged_pos_admin(user):
        return True

    accessible = frappe.db.sql(
        """
        SELECT 1
        FROM `tabPOS Profile` pp
        INNER JOIN `tabPOS Profile User` ppu ON ppu.parent = pp.name
        WHERE pp.company = %s
          AND IFNULL(pp.disabled, 0) = 0
          AND ppu.user = %s
        LIMIT 1
        """,
        (company, user),
    )
    if not accessible:
        frappe.throw(
            _("You don't have access to POS profiles for company {0}.").format(company),
            frappe.PermissionError,
        )
    return True


def require_shift_access(
    shift_name,
    pos_profile=None,
    company=None,
    user=None,
    require_open=True,
):
    """Validate a POS Opening Shift against current user/profile/company.

    Returns the trusted database row.  Client-provided profile/company values
    must never be used as authority for shift-bound operations.
    """
    user = user or _require_authenticated()
    if not shift_name:
        frappe.throw(_("POS Opening Shift is required."), frappe.ValidationError)

    shift = frappe.db.get_value(
        "POS Opening Shift",
        shift_name,
        [
            "name",
            "user",
            "pos_profile",
            "company",
            "status",
            "docstatus",
            "pos_closing_shift",
            "period_start_date",
        ],
        as_dict=True,
    )
    if not shift:
        frappe.throw(_("POS Opening Shift {0} does not exist.").format(shift_name))

    require_pos_profile_access(shift.pos_profile, company=shift.company, user=user)

    if pos_profile and shift.pos_profile != pos_profile:
        frappe.throw(
            _("The POS Opening Shift does not belong to the selected POS Profile."),
            frappe.PermissionError,
        )
    if company and shift.company != company:
        frappe.throw(
            _("The POS Opening Shift does not belong to the selected company."),
            frappe.PermissionError,
        )
    if shift.user != user and not _is_privileged_pos_admin(user):
        frappe.throw(
            _("This POS Opening Shift belongs to another user."),
            frappe.PermissionError,
        )

    if require_open:
        if cint(shift.docstatus) != 1 or shift.status != "Open" or shift.pos_closing_shift:
            frappe.throw(_("The POS Opening Shift is not open."), frappe.ValidationError)

    return shift


def require_customer_read(customer, pos_profile=None):
    """Authorize reading a customer in POS context."""
    _require_authenticated()
    if not customer or not frappe.db.exists("Customer", customer):
        frappe.throw(_("Customer {0} does not exist.").format(customer or ""))

    if pos_profile:
        profile = require_pos_profile_access(pos_profile)
        profile_group = frappe.db.get_value("POS Profile", profile.name, "customer_group")
        if profile_group:
            customer_group = frappe.db.get_value("Customer", customer, "customer_group")
            if customer_group != profile_group:
                frappe.throw(
                    _("This customer is outside the customer group allowed for this POS Profile."),
                    frappe.PermissionError,
                )
        return True

    if not frappe.has_permission("Customer", "read", customer):
        frappe.throw(_("You don't have permission to view this customer."), frappe.PermissionError)
    return True


def require_warehouse_access(warehouse, user=None):
    """Require that ``warehouse`` belongs to a company accessible from POS.

    This protects stock/batch lookup endpoints that receive a warehouse directly
    instead of a POS Profile. Privileged POS administrators retain access.
    """
    user = user or _require_authenticated()
    if not warehouse:
        frappe.throw(_("Warehouse is required."), frappe.ValidationError)

    row = frappe.db.get_value(
        "Warehouse",
        warehouse,
        ["name", "company", "disabled"],
        as_dict=True,
    )
    if not row:
        frappe.throw(_("Warehouse {0} does not exist.").format(warehouse))
    if cint(row.disabled):
        frappe.throw(_("Warehouse {0} is disabled.").format(warehouse))

    if not _is_privileged_pos_admin(user):
        require_company_access(row.company, user=user)

    return row


def require_pos_document_access(doctype, name, ptype="read", pos_profile=None, user=None):
    """Authorize a POS-linked Sales Invoice / Sales Order document.

    POS-linked documents are bounded by their database POS Profile and company,
    not by caller supplied values. Non-POS documents fall back to Frappe's
    native document permission engine.
    """
    user = user or _require_authenticated()
    if doctype not in {"Sales Invoice", "Sales Order"}:
        frappe.throw(_("Document type {0} is not allowed from POS.").format(doctype), frappe.PermissionError)
    if not name:
        frappe.throw(_("Document name is required."), frappe.ValidationError)

    fields = ["name", "company", "pos_profile", "docstatus"]
    if frappe.db.has_column(doctype, "posa_pos_opening_shift"):
        fields.append("posa_pos_opening_shift")

    row = frappe.db.get_value(doctype, name, fields, as_dict=True)
    if not row:
        frappe.throw(_("{0} {1} does not exist.").format(doctype, name))

    if row.pos_profile:
        require_pos_profile_access(row.pos_profile, company=row.company, user=user)
        if pos_profile and row.pos_profile != pos_profile:
            frappe.throw(_("This document belongs to another POS Profile."), frappe.PermissionError)
        return row

    if not frappe.has_permission(doctype, ptype, name):
        frappe.throw(_("You don't have permission to access this document."), frappe.PermissionError)
    return row


def require_pos_profile_config_access(pos_profile, ptype="write", user=None):
    """Require POS assignment plus native DocType permission for configuration writes."""
    user = user or _require_authenticated()
    profile = require_pos_profile_access(pos_profile, user=user)
    if _is_privileged_pos_admin(user):
        return profile
    if not frappe.has_permission("POS Profile", ptype, pos_profile):
        frappe.throw(_("You don't have permission to modify this POS Profile."), frappe.PermissionError)
    return profile
