# Copyright (c) 2026, POS Next and contributors
# For license information, please see license.txt

"""Security helpers for POS payment methods and their GL accounts.

Phase 3 / security point 4 makes the server authoritative for payment wiring.
The browser may select a configured Mode of Payment, but it is never trusted to
choose a GL Account.  Every standard POS payment is resolved from:

    POS Profile -> POS Payment Method -> Mode of Payment -> company account

Wallet rows remain governed by ``pos_next.api.wallet`` because they intentionally
use a Receivable wallet account instead of a normal Cash/Bank settlement account.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

from pos_next.api.security import require_pos_profile_access


_STANDARD_SETTLEMENT_ACCOUNT_TYPES = {"Cash", "Bank"}


def _throw_permission(message):
    frappe.throw(message, frappe.PermissionError)


def _get_mode_details(mode_of_payment):
    if not mode_of_payment:
        frappe.throw(_("Mode of Payment is required."), frappe.ValidationError)

    fields = ["name", "enabled", "type"]
    if frappe.db.has_column("Mode of Payment", "is_wallet_payment"):
        fields.append("is_wallet_payment")

    row = frappe.db.get_value(
        "Mode of Payment",
        mode_of_payment,
        fields,
        as_dict=True,
    )
    if not row:
        frappe.throw(
            _("Mode of Payment {0} does not exist.").format(mode_of_payment),
            frappe.ValidationError,
        )
    if not cint(row.get("enabled")):
        frappe.throw(
            _("Mode of Payment {0} is disabled.").format(mode_of_payment),
            frappe.ValidationError,
        )
    row["is_wallet_payment"] = cint(row.get("is_wallet_payment") or 0)
    return row


def _get_account_details(account_name):
    if not account_name:
        return None
    return frappe.db.get_value(
        "Account",
        account_name,
        ["name", "company", "account_type", "root_type", "is_group", "disabled", "account_currency"],
        as_dict=True,
    )


def resolve_pos_payment_account(
    pos_profile,
    mode_of_payment,
    company=None,
    *,
    allow_wallet=False,
    required_mode_type=None,
    required_account_types=None,
):
    """Resolve the trusted GL account for a POS payment method.

    Security guarantees:
    - the current user can operate the POS Profile;
    - the Mode of Payment is actually present in that profile;
    - the mode is enabled;
    - the company comes from the POS Profile, not the browser;
    - the account comes only from Mode of Payment Account for that company;
    - the account is an active leaf account in the same company;
    - wallet modes are rejected unless the caller explicitly allows them.

    Returns a ``frappe._dict`` with ``account`` plus mode/account metadata.
    """
    profile = require_pos_profile_access(pos_profile, company=company)
    company = profile.company

    if not frappe.db.exists(
        "POS Payment Method",
        {
            "parent": profile.name,
            "parenttype": "POS Profile",
            "mode_of_payment": mode_of_payment,
        },
    ):
        _throw_permission(
            _("Mode of Payment {0} is not configured for POS Profile {1}.").format(
                mode_of_payment or "", profile.name
            )
        )

    mode = _get_mode_details(mode_of_payment)

    if mode.is_wallet_payment and not allow_wallet:
        _throw_permission(
            _("Wallet payment method {0} cannot be used through the standard payment flow.").format(
                mode_of_payment
            )
        )

    if required_mode_type and mode.type != required_mode_type:
        frappe.throw(
            _("Mode of Payment {0} must be of type {1}.").format(
                mode_of_payment, required_mode_type
            ),
            frappe.ValidationError,
        )

    account_name = frappe.db.get_value(
        "Mode of Payment Account",
        {"parent": mode_of_payment, "company": company},
        "default_account",
    )
    if not account_name:
        frappe.throw(
            _("Mode of Payment {0} has no account configured for company {1}.").format(
                mode_of_payment, company
            ),
            frappe.ValidationError,
        )

    account = _get_account_details(account_name)
    if (
        not account
        or account.company != company
        or cint(account.is_group)
        or cint(account.disabled)
    ):
        frappe.throw(
            _("The account configured for Mode of Payment {0} is invalid for company {1}.").format(
                mode_of_payment, company
            ),
            frappe.ValidationError,
        )

    allowed_account_types = (
        set(required_account_types)
        if required_account_types is not None
        else (_STANDARD_SETTLEMENT_ACCOUNT_TYPES if not mode.is_wallet_payment else None)
    )
    if allowed_account_types is not None and account.account_type not in allowed_account_types:
        frappe.throw(
            _("Mode of Payment {0} must use an active Cash or Bank account for this POS Profile.").format(
                mode_of_payment
            ),
            frappe.ValidationError,
        )

    return frappe._dict(
        {
            "pos_profile": profile.name,
            "company": company,
            "mode_of_payment": mode.name,
            "mode_type": mode.type,
            "is_wallet_payment": mode.is_wallet_payment,
            "account": account.name,
            "account_type": account.account_type,
            "account_currency": account.account_currency,
        }
    )


def validate_and_pin_invoice_payments(doc):
    """Validate standard POS payment rows and overwrite client account values.

    Wallet rows are intentionally skipped here and remain validated by the wallet
    security layer.  Every non-wallet row is pinned to the server-configured
    Cash/Bank account for its Mode of Payment.
    """
    # Only enforce POSNext/ERPNext POS payment wiring on invoices that were
    # actually created through a POS frontend. A normal Sales Invoice created
    # from Desk may legitimately have ``is_pos``/``pos_profile`` set (Paid +
    # POS Profile) and must continue to use ERPNext's standard invoice flow.
    if not doc or not doc.get("is_pos") or not doc.get("is_created_using_pos"):
        return
    if not doc.get("pos_profile") or not doc.get("company"):
        frappe.throw(_("POS Profile and company are required for POS payments."))

    for payment in doc.get("payments") or []:
        amount = flt(payment.get("amount") or 0)
        mode_of_payment = payment.get("mode_of_payment")

        # Ignore truly empty placeholder rows, but never allow an amount without a mode.
        if not mode_of_payment and abs(amount) <= 0.0000001:
            continue
        if not mode_of_payment:
            frappe.throw(_("Mode of Payment is required for every non-zero POS payment."))

        mode = _get_mode_details(mode_of_payment)
        if mode.is_wallet_payment:
            # Point 2 validates wallet mode/profile/account/balance authoritatively.
            continue

        details = resolve_pos_payment_account(
            doc.pos_profile,
            mode_of_payment,
            company=doc.company,
            allow_wallet=False,
        )

        # The browser-provided account/type are never authoritative. Pin the row
        # to the configured server-side payment wiring.
        payment.account = details.account
        if hasattr(payment, "type"):
            payment.type = details.mode_type


def validate_requested_payment_account(expected_account, requested_account):
    """Reject a client-supplied account when it differs from the trusted account."""
    if requested_account and requested_account != expected_account:
        _throw_permission(
            _("Payment account cannot be overridden from POS. The configured account must be used.")
        )
    return expected_account
