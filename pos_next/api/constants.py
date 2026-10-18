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
	"default_customer_group",
	"hide_unavailable_items",
	"print_receipt_on_order_complete",
	"allow_delete_draft_invoices",
	"enable_auto_stock_sync",
	"stock_sync_interval",
	"customer_display_enabled",
	"customer_display_company_name",
	"customer_display_welcome_text",
	"customer_display_pos_location",
	"customer_display_theme",
	"customer_display_size_mode",
	"customer_display_currency_label",
	"customer_display_idle_mode",
	"customer_display_idle_image",
	"customer_display_idle_video",
	"customer_display_overlay_enabled",
	"customer_display_overlay_text",
	"customer_display_overlay_type",
	"customer_display_overlay_on",
	"customer_display_overlay_position",
	"customer_display_overlay_text_color",
	"customer_display_overlay_background_color",
	"customer_display_overlay_opacity",
	"customer_display_overlay_font_size",
	"customer_display_overlay_scroll_speed",
	"customer_display_thank_you_duration",
	"cd_show_company_name",
	"cd_show_welcome_text",
	"cd_show_pos_location",
	"cd_show_pos_number",
	"cd_show_product_image",
	"cd_show_item_name",
	"cd_show_barcode",
	"cd_show_quantity",
	"cd_show_original_price",
	"cd_show_discount_amount",
	"cd_show_discount_percentage",
	"cd_show_final_price",
	"cd_show_running_qty",
	"cd_show_subtotal",
	"cd_show_total_discount",
	"cd_show_grand_total",
	"cd_show_customer_name",
	"cd_customer_name_mode",
	"cd_show_loyalty_points",
	"cd_show_loyalty_earned",
	"cd_show_customer_credit",
	"cd_show_payment_method",
	"cd_show_amount_paid",
	"cd_show_remaining_balance",
	"cd_show_change",
	"cd_show_invoice_number",
	"cd_enable_thank_you",
	"customer_display_thank_you_title",
	"customer_display_thank_you_message",
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
	"default_customer_group": "",
	"hide_unavailable_items": 0,
	"print_receipt_on_order_complete": 0,
	"allow_delete_draft_invoices": 0,
	"enable_auto_stock_sync": 0,
	"stock_sync_interval": 60,
	"customer_display_enabled": 0,
	"customer_display_company_name": "MUBTKIR",
	"customer_display_welcome_text": "Welcome",
	"customer_display_pos_location": "",
	"customer_display_theme": "Dark",
	"customer_display_size_mode": "Auto",
	"customer_display_currency_label": "SAR",
	"customer_display_idle_mode": "Welcome",
	"customer_display_idle_image": "",
	"customer_display_idle_video": "",
	"customer_display_overlay_enabled": 0,
	"customer_display_overlay_text": "",
	"customer_display_overlay_type": "Scrolling",
	"customer_display_overlay_on": "All",
	"customer_display_overlay_position": "Bottom",
	"customer_display_overlay_text_color": "#FFFFFF",
	"customer_display_overlay_background_color": "#000000",
	"customer_display_overlay_opacity": 65,
	"customer_display_overlay_font_size": 28,
	"customer_display_overlay_scroll_speed": "Normal",
	"customer_display_thank_you_duration": 5,
	"cd_show_company_name": 1,
	"cd_show_welcome_text": 1,
	"cd_show_pos_location": 1,
	"cd_show_pos_number": 1,
	"cd_show_product_image": 1,
	"cd_show_item_name": 1,
	"cd_show_barcode": 1,
	"cd_show_quantity": 1,
	"cd_show_original_price": 1,
	"cd_show_discount_amount": 1,
	"cd_show_discount_percentage": 0,
	"cd_show_final_price": 1,
	"cd_show_running_qty": 1,
	"cd_show_subtotal": 1,
	"cd_show_total_discount": 1,
	"cd_show_grand_total": 1,
	"cd_show_customer_name": 1,
	"cd_customer_name_mode": "First Name",
	"cd_show_loyalty_points": 1,
	"cd_show_loyalty_earned": 1,
	"cd_show_customer_credit": 1,
	"cd_show_payment_method": 1,
	"cd_show_amount_paid": 1,
	"cd_show_remaining_balance": 1,
	"cd_show_change": 1,
	"cd_show_invoice_number": 1,
	"cd_enable_thank_you": 1,
	"customer_display_thank_you_title": "Thank You",
	"customer_display_thank_you_message": "Thank you for shopping with us",
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
