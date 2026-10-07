# -*- coding: utf-8 -*-
# Copyright (c) 2025, BrainWise and contributors
# For license information, please see license.txt

"""POS Cash Disbursement API.

Phase 3 / security point 4 keeps every accounting decision on the server:
- the opening shift is the authority for profile/company/cashier;
- cash disbursement must be enabled in POS Settings;
- the cash Mode of Payment must belong to the POS Profile and be enabled;
- its Cash GL account is resolved from Mode of Payment Account;
- the debit account comes only from POS Settings and cannot be overridden;
- both GL accounts are validated as active leaf accounts in the same company.
"""

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt, nowdate

from pos_next.api.payment_security import resolve_pos_payment_account
from pos_next.api.security import (
    require_company_access,
    require_pos_profile_access,
    require_shift_access,
    user_has_pos_profile_access,
)

# Marker prefix used in user_remark to identify POS disbursement entries
_MARKER = "pos_cash_disbursement"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_disbursement_settings(pos_profile):
    """Return trusted cash-disbursement configuration for a POS Profile."""
    settings = frappe.db.get_value(
        "POS Settings",
        {"pos_profile": pos_profile, "enabled": 1},
        ["name", "allow_cash_disbursement", "cash_disbursement_account"],
        as_dict=True,
    )
    if not settings or not cint(settings.allow_cash_disbursement):
        frappe.throw(
            _("Cash disbursement is disabled for this POS Profile."),
            frappe.PermissionError,
        )
    if not settings.cash_disbursement_account:
        frappe.throw(
            _("Please configure Cash Disbursement Account in POS Settings first."),
            title=_("Missing Disbursement Account"),
        )
    return settings


def _get_cash_mode(pos_profile):
    """Return the profile's trusted cash Mode of Payment.

    Prefer the explicit POSNext field. If it is empty, choose the first payment
    method on the profile whose ERPNext Mode of Payment type is ``Cash``.
    Never fall back to a hard-coded mode name that is not configured on profile.
    """
    configured = frappe.db.get_value("POS Profile", pos_profile, "posa_cash_mode_of_payment")
    if configured:
        return configured

    payment_methods = frappe.get_all(
        "POS Payment Method",
        filters={"parent": pos_profile, "parenttype": "POS Profile"},
        fields=["mode_of_payment"],
        order_by="idx asc",
    )
    for row in payment_methods:
        mode = frappe.db.get_value(
            "Mode of Payment",
            row.mode_of_payment,
            ["enabled", "type"],
            as_dict=True,
        )
        if mode and cint(mode.enabled) and mode.type == "Cash":
            return row.mode_of_payment

    frappe.throw(
        _("No enabled Cash Mode of Payment is configured for this POS Profile."),
        frappe.ValidationError,
    )


def _get_cash_account(pos_profile, company):
    """Return and validate the Cash GL account used by the current POS Profile."""
    cash_mode = _get_cash_mode(pos_profile)
    details = resolve_pos_payment_account(
        pos_profile,
        cash_mode,
        company=company,
        allow_wallet=False,
        required_mode_type="Cash",
        required_account_types={"Cash"},
    )
    return details.account, cash_mode


def _validate_disbursement_account(account_name, company, cash_account=None):
    """Validate the server-configured debit account for a cash disbursement.

    The dialog does not collect Party details, so Receivable/Payable accounts are
    deliberately rejected. Cash/Bank accounts are also rejected as debit targets
    to keep this feature a true expense/advance disbursement instead of an
    unrestricted cash-transfer mechanism.
    """
    account = frappe.db.get_value(
        "Account",
        account_name,
        ["name", "company", "account_type", "root_type", "is_group", "disabled"],
        as_dict=True,
    )
    if (
        not account
        or account.company != company
        or cint(account.is_group)
        or cint(account.disabled)
    ):
        frappe.throw(
            _("Invalid cash disbursement account for this company."),
            frappe.PermissionError,
        )

    if account.name == cash_account:
        frappe.throw(
            _("Cash disbursement debit account cannot be the same as the POS cash account."),
            frappe.ValidationError,
        )

    if account.root_type not in {"Asset", "Expense"}:
        frappe.throw(
            _("Cash Disbursement Account must be an Asset or Expense account."),
            frappe.ValidationError,
        )

    if account.account_type in {"Receivable", "Payable", "Cash", "Bank"}:
        frappe.throw(
            _("Cash Disbursement Account cannot be a Receivable, Payable, Cash, or Bank account."),
            frappe.ValidationError,
        )

    return account


def _get_disbursement_account(pos_profile, company, cash_account=None):
    """Return the trusted debit account from enabled POS Settings."""
    settings = _get_disbursement_settings(pos_profile)
    account_name = settings.cash_disbursement_account
    _validate_disbursement_account(account_name, company, cash_account=cash_account)
    return account_name


def _remark(shift_name, reason):
    return f"{_MARKER}|{shift_name}|{reason}"


def _parse_remark(remark):
    parts = cstr(remark).split("|", 2)
    if len(parts) < 3 or parts[0] != _MARKER:
        return None, None
    return parts[1], parts[2]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@frappe.whitelist()
def create_cash_disbursement(
    shift_name,
    amount,
    reason,
    pos_profile=None,
    company=None,
    disbursement_account=None,
):
    """Create a Journal Entry recording cash paid out from the active POS shift."""
    amount = flt(amount)
    if amount <= 0:
        frappe.throw(_("Disbursement amount must be greater than zero."))

    reason = cstr(reason).strip()
    if not reason:
        frappe.throw(_("Please provide a reason for the cash disbursement."))
    reason = reason[:500]

    if not shift_name:
        frappe.throw(_("No active POS shift found."))

    # The database shift is authoritative; client profile/company are only
    # consistency checks and may be omitted by newer clients.
    shift = require_shift_access(
        shift_name,
        pos_profile=pos_profile,
        company=company,
        require_open=True,
    )
    pos_profile = shift.pos_profile
    company = shift.company

    # Feature flag + both accounts come from trusted configuration.
    _get_disbursement_settings(pos_profile)
    cash_account, cash_mode = _get_cash_account(pos_profile, company)
    configured_debit_account = _get_disbursement_account(
        pos_profile,
        company,
        cash_account=cash_account,
    )

    if disbursement_account and disbursement_account != configured_debit_account:
        frappe.throw(
            _("Cash disbursement account cannot be overridden from POS."),
            frappe.PermissionError,
        )
    debit_account = configured_debit_account

    # Resolve cost center from Company. ERPNext will enforce any additional
    # accounting-dimension requirements during Journal Entry validation.
    cost_center = frappe.get_cached_value("Company", company, "cost_center")

    je = frappe.new_doc("Journal Entry")
    je.voucher_type = "Cash Entry"
    je.company = company
    je.posting_date = nowdate()
    je.user_remark = _remark(shift_name, reason)
    je.cheque_no = shift_name
    je.cheque_date = nowdate()

    je.append(
        "accounts",
        {
            "account": debit_account,
            "debit_in_account_currency": amount,
            "credit_in_account_currency": 0,
            "cost_center": cost_center,
            "user_remark": reason,
        },
    )
    je.append(
        "accounts",
        {
            "account": cash_account,
            "debit_in_account_currency": 0,
            "credit_in_account_currency": amount,
            "cost_center": cost_center,
            "user_remark": reason,
        },
    )

    try:
        # Cashiers may not have broad Journal Entry Desk rights. The bypass is
        # bounded by the authenticated open-shift/profile/company checks above.
        je.flags.ignore_permissions = True
        try:
            je.insert(ignore_permissions=True)
            je.submit()
        finally:
            je.flags.ignore_permissions = False
    except frappe.exceptions.ValidationError as e:
        err_msg = str(e).lower()
        if "party" in err_msg or "الطرف" in err_msg or "نوع الطرف" in err_msg:
            frappe.throw(
                _(
                    "The configured Disbursement Account requires a Party. "
                    "Please use a non-party Asset or Expense account in POS Settings."
                ),
                title=_("Invalid Account Configuration"),
            )
        raise

    frappe.logger().info(
        "POS Cash Disbursement: %s | shift=%s | profile=%s | cash_mode=%s | amount=%s",
        je.name,
        shift_name,
        pos_profile,
        cash_mode,
        amount,
    )

    return {
        "name": je.name,
        "amount": amount,
        "reason": reason,
        "journal_entry": je.name,
        "posting_date": je.posting_date,
        "mode_of_payment": cash_mode,
    }


@frappe.whitelist()
def get_shift_disbursements(shift_name):
    """Return submitted disbursements linked to an authorized POS shift."""
    require_shift_access(shift_name, require_open=False)
    marker_prefix = f"{_MARKER}|{shift_name}|%"

    rows = frappe.db.sql(
        """
        SELECT name, posting_date, user_remark, total_debit AS amount
        FROM `tabJournal Entry`
        WHERE user_remark LIKE %s
          AND docstatus = 1
        ORDER BY creation ASC
        """,
        (marker_prefix,),
        as_dict=True,
    )

    result = []
    for row in rows:
        _, reason = _parse_remark(row.user_remark)
        result.append(
            {
                "name": row.name,
                "posting_date": str(row.posting_date),
                "amount": flt(row.amount),
                "reason": reason or "",
            }
        )
    return result


@frappe.whitelist()
def cancel_disbursement(journal_entry_name):
    """Cancel a POS cash-disbursement Journal Entry while its shift is open."""
    je = frappe.get_doc("Journal Entry", journal_entry_name)
    if je.docstatus != 1:
        frappe.throw(_("This disbursement entry is not submitted and cannot be cancelled."))

    shift_name, _ = _parse_remark(je.user_remark or "")
    if not shift_name:
        frappe.throw(
            _("This Journal Entry is not a POS cash disbursement."),
            frappe.PermissionError,
        )

    shift = require_shift_access(shift_name, require_open=True)
    if (
        je.company != shift.company
        or je.cheque_no != shift.name
        or je.voucher_type != "Cash Entry"
    ):
        frappe.throw(
            _("This Journal Entry is not a valid disbursement for the current POS shift."),
            frappe.PermissionError,
        )

    je.flags.ignore_permissions = True
    try:
        je.cancel()
    finally:
        je.flags.ignore_permissions = False
    return {"status": "cancelled", "name": journal_entry_name}


@frappe.whitelist()
def get_disbursement_accounts(company=None, pos_profile=None):
    """Return only server-configured disbursement accounts visible to this user.

    Older clients may call this endpoint by company. Newer clients should pass
    ``pos_profile``. Unlike the previous implementation this never exposes the
    company's whole chart of accounts to a cashier.
    """
    profiles = []

    if pos_profile:
        profile = require_pos_profile_access(pos_profile, company=company)
        company = profile.company
        profiles = [profile.name]
    else:
        require_company_access(company)
        filters = {"company": company, "disabled": 0}
        profile_names = frappe.get_all("POS Profile", filters=filters, pluck="name")
        profiles = [p for p in profile_names if user_has_pos_profile_access(p)]

    if not profiles:
        return []

    rows = frappe.get_all(
        "POS Settings",
        filters={
            "pos_profile": ["in", profiles],
            "enabled": 1,
            "allow_cash_disbursement": 1,
        },
        fields=["pos_profile", "cash_disbursement_account"],
    )

    result = []
    seen = set()
    for row in rows:
        account_name = row.cash_disbursement_account
        if not account_name or account_name in seen:
            continue
        account = frappe.db.get_value(
            "Account",
            account_name,
            ["name", "account_name", "account_type", "root_type", "company", "is_group", "disabled"],
            as_dict=True,
        )
        if not account or account.company != company or cint(account.is_group) or cint(account.disabled):
            continue
        if account.root_type not in {"Asset", "Expense"}:
            continue
        if account.account_type in {"Receivable", "Payable", "Cash", "Bank"}:
            continue
        seen.add(account.name)
        result.append(
            {
                "name": account.name,
                "account_name": account.account_name,
                "account_type": account.account_type,
                "root_type": account.root_type,
            }
        )
    return result


@frappe.whitelist()
def get_total_disbursements(shift_name):
    """Return total submitted cash disbursements for an authorized shift."""
    require_shift_access(shift_name, require_open=False)
    marker_prefix = f"{_MARKER}|{shift_name}|%"
    result = frappe.db.sql(
        """
        SELECT COALESCE(SUM(total_debit), 0) AS total
        FROM `tabJournal Entry`
        WHERE user_remark LIKE %s
          AND docstatus = 1
        """,
        (marker_prefix,),
        as_dict=True,
    )
    return flt(result[0].total) if result else 0.0
