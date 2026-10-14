# -*- coding: utf-8 -*-
# Copyright (c) 2024, POS Next and contributors
# For license information, please see license.txt

"""
Shared constants for POS Next API modules.

This module contains shared constants, field lists, and default values
used across multiple API modules to maintain DRY principles.

Note: Some settings are derived from POS Profile as single source of truth:
- allow_write_off_change: derived from POS Profile (write_off_account + write_off_limit > 0)
- disable_rounded_total: uses POS Profile value directly
- Discount/rate policy: derived from POS Profile only (mu_allow_item_discount,
  mu_allow_additional_discount, mu_max_discount_percent, mu_use_percentage_discount,
  allow_rate_change). The old POS Settings discount fields were removed; the API
  keys are still returned for frontend compatibility but are computed from the profile.
"""

# Fields to fetch from POS Settings
# Used by both bootstrap.py and pos_profile.py
POS_SETTINGS_FIELDS = [
	"name",
	"enabled",
	"tax_inclusive",
	"allow_credit_sale",
	"allow_customer_credit_payment",
	"allow_return",
	"allow_partial_payment",
	"use_exact_amount",
	"decimal_precision",
	"allow_negative_stock",
	"enable_sales_persons",
	"silent_print",
	"allow_print_draft_invoices",
	"allow_sales_order",
	"allow_select_sales_order",
	"create_only_sales_order",
	"enable_session_lock",
	"session_lock_timeout",
	"show_variants_as_items",
	"allow_cash_disbursement",
	"cash_disbursement_account",
	"default_customer_group",
	"hide_unavailable_items",
	"print_receipt_on_order_complete",
	"allow_delete_draft_invoices",
	"enable_auto_stock_sync",
	"stock_sync_interval",
]

# Default POS Settings values
# Used when no POS Settings found or on error
DEFAULT_POS_SETTINGS = {
	"enabled": 0,
	"tax_inclusive": 0,
	# Discount/rate keys kept for frontend API compatibility.
	# Their effective values are always recomputed from POS Profile.
	"allow_user_to_edit_additional_discount": 0,
	"allow_user_to_edit_item_discount": 1,
	"allow_user_to_edit_rate": 0,
	"use_percentage_discount": 0,
	"max_discount_allowed": 0,
	"disable_rounded_total": 0,  # Derived from POS Profile
	"allow_credit_sale": 0,
	"allow_customer_credit_payment": 0,
	"allow_return": 0,
	"allow_write_off_change": 0,  # Derived from POS Profile
	"allow_partial_payment": 0,
	"use_exact_amount": 0,
	"decimal_precision": "2",
	"allow_negative_stock": 0,
	"enable_sales_persons": "Disabled",
	"silent_print": 0,
	"allow_print_draft_invoices": 0,
	"allow_sales_order": 0,
	"allow_select_sales_order": 0,
	"create_only_sales_order": 0,
	"enable_session_lock": 0,
	"session_lock_timeout": 5,
	"show_variants_as_items": 0,
	"allow_cash_disbursement": 0,
	"cash_disbursement_account": "",
	"default_customer_group": "",
	"hide_unavailable_items": 0,
	"print_receipt_on_order_complete": 0,
	"allow_delete_draft_invoices": 0,
	"enable_auto_stock_sync": 0,
	"stock_sync_interval": 60,
}


# Single shared helper: effective discount/rate policy comes from POS Profile only.
# (قرار الجرد: الخصومات وتعديل السعر تُدار من البروفايل فقط)
def apply_profile_discount_policy(settings, profile_doc):
	"""Overwrite the discount/rate keys of a settings dict from the POS Profile.

	``settings`` is mutated and returned. ``profile_doc`` must be a POS Profile
	document (or any object supporting .get()).
	"""
	from frappe.utils import cint, flt

	settings["allow_user_to_edit_item_discount"] = cint(
		profile_doc.get("mu_allow_item_discount") or 0
	)
	settings["allow_user_to_edit_additional_discount"] = cint(
		profile_doc.get("mu_allow_additional_discount") or 0
	)
	# ERPNext POS Profile "Allow User to Edit Rate" is the single switch.
	settings["allow_rate_change"] = cint(profile_doc.get("allow_rate_change") or 0)
	settings["allow_user_to_edit_rate"] = settings["allow_rate_change"]
	# Branch ceiling is the only discount limit (0 = unlimited).
	settings["max_discount_allowed"] = flt(profile_doc.get("mu_max_discount_percent") or 0)
	settings["use_percentage_discount"] = cint(profile_doc.get("mu_use_percentage_discount") or 0)
	return settings
