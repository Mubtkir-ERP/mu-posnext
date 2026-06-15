# -*- coding: utf-8 -*-
# Copyright (c) 2025, BrainWise and contributors
# For license information, please see license.txt

"""
POS Cash Disbursement API

Allows cashiers to record cash given out (e.g., employee advances, petty expenses)
directly from the POS session. Creates a real Journal Entry that:
  - Debits the configured disbursement account (expense / advance account)
  - Credits the cash account linked to the POS cash Mode of Payment

The Journal Entry is linked to the POS Opening Shift via user_remark so it can
be subtracted from the expected cash balance in the closing shift report.
"""

import frappe
from frappe import _
from frappe.utils import flt, nowdate, get_datetime

# Marker prefix used in user_remark to identify POS disbursement entries
_MARKER = "pos_cash_disbursement"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_cash_account(pos_profile, company):
    """Return the GL account linked to the cash Mode of Payment for this profile."""
    cash_mode = (
        frappe.get_value("POS Profile", pos_profile, "posa_cash_mode_of_payment")
        or "Cash"
    )
    account = frappe.db.get_value(
        "Mode of Payment Account",
        {"parent": cash_mode, "company": company},
        "default_account",
    )
    if not account:
        frappe.throw(
            _("Cash account is not configured for Mode of Payment '{0}'. "
              "Please set a default account in Mode of Payment settings.").format(cash_mode),
            title=_("Missing Cash Account"),
        )
    return account


def _get_disbursement_account(pos_profile, company):
    """Return the debit (expense/advance) account for disbursements.

    Priority:
    1. POS Settings > cash_disbursement_account (per-profile setting)
    2. Company default cost of revenue account
    Raises an error if nothing is configured.
    """
    # Check POS Settings for an explicit account linked to the current profile
    disbursement_account = frappe.db.get_value(
        "POS Settings",
        {"pos_profile": pos_profile, "enabled": 1},
        "cash_disbursement_account"
    )
    if disbursement_account:
        return disbursement_account

    # Fallback — caller must provide it
    frappe.throw(
        _("Please configure Cash Disbursement Account in POS Settings first."),
        title=_("Missing Disbursement Account"),
    )


def _remark(shift_name, reason):
    return f"{_MARKER}|{shift_name}|{reason}"


def _parse_remark(remark):
    parts = remark.split("|", 2)
    if len(parts) < 3 or parts[0] != _MARKER:
        return None, None
    return parts[1], parts[2]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@frappe.whitelist()
def create_cash_disbursement(shift_name, amount, reason, pos_profile, company, disbursement_account=None):
    """Create a Journal Entry recording a cash disbursement from the POS shift.

    Args:
        shift_name (str): POS Opening Shift name
        amount (float): Amount disbursed (must be > 0)
        reason (str): Description / reason for disbursement
        pos_profile (str): POS Profile name (to resolve cash account)
        company (str): Company name
        disbursement_account (str, optional): GL account to debit.
            Falls back to POS Settings if omitted.

    Returns:
        dict: {name, amount, reason, journal_entry}
    """
    amount = flt(amount)
    if amount <= 0:
        frappe.throw(_("Disbursement amount must be greater than zero."))
    if not reason or not reason.strip():
        frappe.throw(_("Please provide a reason for the cash disbursement."))
    if not shift_name:
        frappe.throw(_("No active POS shift found."))

    # Resolve accounts
    cash_account = _get_cash_account(pos_profile, company)
    debit_account = disbursement_account or _get_disbursement_account(pos_profile, company)

    # Resolve cost center
    cost_center = frappe.get_cached_value("Company", company, "cost_center")

    # Build Journal Entry
    je = frappe.new_doc("Journal Entry")
    je.voucher_type = "Cash Entry"
    je.company = company
    je.posting_date = nowdate()
    je.user_remark = _remark(shift_name, reason.strip())
    je.cheque_no = shift_name          # for quick lookup / filtering in reports
    je.cheque_date = nowdate()

    je.append("accounts", {
        "account": debit_account,
        "debit_in_account_currency": amount,
        "credit_in_account_currency": 0,
        "cost_center": cost_center,
        "user_remark": reason.strip(),
    })
    je.append("accounts", {
        "account": cash_account,
        "debit_in_account_currency": 0,
        "credit_in_account_currency": amount,
        "cost_center": cost_center,
        "user_remark": reason.strip(),
    })

    try:
        je.insert(ignore_permissions=True)
        je.submit()
    except frappe.exceptions.ValidationError as e:
        # If it's a party error (due to using Receivable/Payable account without party)
        err_msg = str(e).lower()
        if "party" in err_msg or "الطرف" in err_msg or "نوع الطرف" in err_msg:
            frappe.throw(
                _("The configured Disbursement Account requires a Party (Customer/Supplier/Employee). Please use an Expense or Cash account instead in POS Settings."),
                title=_("Invalid Account Configuration")
            )
        else:
            raise

    frappe.logger().info(
        f"POS Cash Disbursement: {je.name} | shift={shift_name} | amount={amount} | reason={reason}"
    )

    return {
        "name": je.name,
        "amount": amount,
        "reason": reason.strip(),
        "journal_entry": je.name,
        "posting_date": je.posting_date,
    }


@frappe.whitelist()
def get_shift_disbursements(shift_name):
    """Return all submitted cash disbursements linked to a POS shift.

    Args:
        shift_name (str): POS Opening Shift name

    Returns:
        list[dict]: [{name, amount, reason, posting_date}, ...]
    """
    marker_prefix = f"{_MARKER}|{shift_name}|%"

    rows = frappe.db.sql(
        """
        SELECT name, posting_date, user_remark, total_debit AS amount
        FROM `tabJournal Entry`
        WHERE user_remark LIKE %s
          AND docstatus = 1
        ORDER BY creation ASC
        """,
        marker_prefix,
        as_dict=True,
    )

    result = []
    for row in rows:
        _, reason = _parse_remark(row.user_remark)
        result.append({
            "name": row.name,
            "posting_date": str(row.posting_date),
            "amount": flt(row.amount),
            "reason": reason or "",
        })
    return result


@frappe.whitelist()
def cancel_disbursement(journal_entry_name):
    """Cancel (reverse) a disbursement Journal Entry.

    Only allowed while the POS shift is still open.

    Args:
        journal_entry_name (str): Journal Entry name

    Returns:
        dict: {status}
    """
    je = frappe.get_doc("Journal Entry", journal_entry_name)
    if je.docstatus != 1:
        frappe.throw(_("This disbursement entry is not submitted and cannot be cancelled."))

    # Verify shift is still open
    shift_name, _ = _parse_remark(je.user_remark or "")
    if shift_name:
        shift_status = frappe.db.get_value("POS Opening Shift", shift_name, "status")
        if shift_status and shift_status != "Open":
            frappe.throw(
                _("Cannot cancel a disbursement after the POS shift has been closed."),
                title=_("Shift Closed"),
            )

    je.cancel()
    return {"status": "cancelled", "name": journal_entry_name}


@frappe.whitelist()
def get_disbursement_accounts(company):
    """Return candidate accounts for cash disbursements (expense / current asset types).

    Used to populate the account selector in the POS dialog.

    Args:
        company (str): Company name

    Returns:
        list[dict]: [{name, account_name, account_type}, ...]
    """
    accounts = frappe.db.get_all(
        "Account",
        filters={
            "company": company,
            "is_group": 0,
            "disabled": 0,
            "account_type": ["in", [
                "Expense Account",
                "Expenses Included In Asset Valuation",
                "Temporary",
                "Cash",
                "Bank",
                "Receivable",
            ]],
        },
        fields=["name", "account_name", "account_type"],
        order_by="account_name",
    )
    return accounts


@frappe.whitelist()
def get_total_disbursements(shift_name):
    """Return the total amount of all disbursements for a shift.

    Used by the closing shift to adjust the expected cash balance.

    Args:
        shift_name (str): POS Opening Shift name

    Returns:
        float: Total disbursed amount
    """
    marker_prefix = f"{_MARKER}|{shift_name}|%"
    result = frappe.db.sql(
        """
        SELECT COALESCE(SUM(total_debit), 0) AS total
        FROM `tabJournal Entry`
        WHERE user_remark LIKE %s
          AND docstatus = 1
        """,
        marker_prefix,
        as_dict=True,
    )
    return flt(result[0].total) if result else 0.0
