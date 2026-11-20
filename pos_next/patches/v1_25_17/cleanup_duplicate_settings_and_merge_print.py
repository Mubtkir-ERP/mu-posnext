# Copyright (c) 2026, Mubtkir and contributors
# For license information, please see license.txt

"""Consolidate POS Settings vs POS Profile fields and remove duplicate custom fields."""

import frappe
from frappe.utils import cint


PROFILE_TO_SETTINGS_FIELDS = (
	"mu_voucher_enabled",
	"mu_voucher_whatsapp_enabled",
	"mu_voucher_otp_enabled",
	"mu_voucher_low_balance_threshold",
	"mu_voucher_expiry_reminder_days",
	"mu_delivery_otp_enabled",
)

SETTINGS_TO_PROFILE_FIELDS = (
	"mu_voucher_redeem_item",
	"mu_voucher_warehouse",
	"mu_voucher_daily_limit",
)

OBSOLETE_PROFILE_CUSTOM_FIELDS = PROFILE_TO_SETTINGS_FIELDS + (
	"mu_voucher_section",
	"mu_posnext_communications_section",
	"mu_print_formats_section",
	"mu_allow_shift_closing_print",
)


def _migrate_voucher_values():
	"""Preserve existing configuration values before removing duplicate columns."""
	settings_rows = frappe.get_all(
		"POS Settings",
		fields=["name", "pos_profile"],
		order_by="enabled desc, modified desc",
	)
	ps_by_profile = {}
	for row in settings_rows:
		if row.pos_profile and row.pos_profile not in ps_by_profile:
			ps_by_profile[row.pos_profile] = row.name

	for profile_name, ps_name in ps_by_profile.items():
		for field in SETTINGS_TO_PROFILE_FIELDS:
			if frappe.db.has_column("POS Settings", field) and frappe.db.has_column("POS Profile", field):
				ps_val = frappe.db.get_value("POS Settings", ps_name, field)
				prof_val = frappe.db.get_value("POS Profile", profile_name, field)
				if ps_val and not prof_val:
					frappe.db.set_value("POS Profile", profile_name, field, ps_val, update_modified=False)

		for field in PROFILE_TO_SETTINGS_FIELDS:
			if frappe.db.has_column("POS Profile", field) and frappe.db.has_column("POS Settings", field):
				prof_val = frappe.db.get_value("POS Profile", profile_name, field)
				ps_val = frappe.db.get_value("POS Settings", ps_name, field)
				if prof_val and not cint(ps_val):
					frappe.db.set_value("POS Settings", ps_name, field, prof_val, update_modified=False)


def _drop_obsolete_custom_fields():
	"""Remove duplicate Custom Fields from POS Profile and moved columns from POS Settings."""
	for fieldname in OBSOLETE_PROFILE_CUSTOM_FIELDS:
		cf_name = frappe.db.get_value(
			"Custom Field",
			{"dt": "POS Profile", "fieldname": fieldname},
			"name",
		)
		if cf_name:
			frappe.delete_doc("Custom Field", cf_name, ignore_permissions=True, force=True)
		if frappe.db.has_column("POS Profile", fieldname):
			frappe.db.sql_ddl(f"ALTER TABLE `tabPOS Profile` DROP COLUMN `{fieldname}`")

	for fieldname in SETTINGS_TO_PROFILE_FIELDS:
		if frappe.db.has_column("POS Settings", fieldname):
			frappe.db.sql_ddl(f"ALTER TABLE `tabPOS Settings` DROP COLUMN `{fieldname}`")


def execute():
	_migrate_voucher_values()
	_drop_obsolete_custom_fields()
	frappe.clear_cache(doctype="POS Profile")
	frappe.clear_cache(doctype="POS Settings")
