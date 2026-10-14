# Copyright (c) 2026, POS Next and contributors
# License: see license.txt

"""Migrate field ownership per the approved settings audit:

POS Profile -> POS Settings:
    - mu_tax_inclusive            -> tax_inclusive
    - mu_default_customer_group   -> default_customer_group
    - posa_allow_delete           -> allow_delete_draft_invoices

POS Settings -> POS Profile:
    - use_percentage_discount     -> mu_use_percentage_discount
    - max_discount_allowed        -> mu_max_discount_percent (only when the
      profile has no branch limit yet; the branch value always wins)

Finally the moved POS Profile custom fields are deleted.
"""

import frappe
from frappe.utils import cint, flt

REMOVED_PROFILE_FIELDS = (
	"POS Profile-mu_tax_inclusive",
	"POS Profile-mu_default_customer_group",
	"POS Profile-posa_allow_delete",
)


def execute():
	_migrate_profile_values_to_settings()
	_migrate_settings_values_to_profile()
	_delete_removed_custom_fields()


def _migrate_profile_values_to_settings():
	has = {
		"tax": frappe.db.has_column("POS Profile", "mu_tax_inclusive"),
		"group": frappe.db.has_column("POS Profile", "mu_default_customer_group"),
		"delete": frappe.db.has_column("POS Profile", "posa_allow_delete"),
	}
	if not any(has.values()):
		return

	fields = ["name"]
	if has["tax"]:
		fields.append("mu_tax_inclusive")
	if has["group"]:
		fields.append("mu_default_customer_group")
	if has["delete"]:
		fields.append("posa_allow_delete")

	for profile in frappe.get_all("POS Profile", fields=fields):
		settings_name = frappe.db.get_value(
			"POS Settings", {"pos_profile": profile.name}, "name"
		)
		if not settings_name:
			continue
		updates = {}
		if has["tax"]:
			updates["tax_inclusive"] = cint(profile.get("mu_tax_inclusive") or 0)
		if has["group"] and profile.get("mu_default_customer_group"):
			updates["default_customer_group"] = profile.mu_default_customer_group
		if has["delete"]:
			updates["allow_delete_draft_invoices"] = cint(profile.get("posa_allow_delete") or 0)
		if updates:
			frappe.db.set_value("POS Settings", settings_name, updates, update_modified=False)


def _ensure_use_percentage_field():
	"""Custom-field sync runs after post_model_sync patches, so create the
	target field here when it does not exist yet (idempotent)."""
	if frappe.db.has_column("POS Profile", "mu_use_percentage_discount"):
		return
	from frappe.custom.doctype.custom_field.custom_field import create_custom_field

	create_custom_field(
		"POS Profile",
		{
			"fieldname": "mu_use_percentage_discount",
			"fieldtype": "Check",
			"label": "استخدام الخصم بالنسبة المئوية",
			"insert_after": "mu_max_discount_percent",
			"default": "0",
		},
	)


def _migrate_settings_values_to_profile():
	has_pct = frappe.db.has_column("POS Settings", "use_percentage_discount")
	has_max = frappe.db.has_column("POS Settings", "max_discount_allowed")
	if not (has_pct or has_max):
		return

	if has_pct:
		_ensure_use_percentage_field()
	if not frappe.db.has_column("POS Profile", "mu_max_discount_percent"):
		has_max = False

	fields = ["name", "pos_profile"]
	if has_pct:
		fields.append("use_percentage_discount")
	if has_max:
		fields.append("max_discount_allowed")

	for settings in frappe.get_all("POS Settings", fields=fields):
		if not settings.pos_profile or not frappe.db.exists("POS Profile", settings.pos_profile):
			continue
		updates = {}
		if has_pct:
			updates["mu_use_percentage_discount"] = cint(settings.get("use_percentage_discount") or 0)
		if has_max and flt(settings.get("max_discount_allowed") or 0) > 0:
			current = flt(
				frappe.db.get_value("POS Profile", settings.pos_profile, "mu_max_discount_percent") or 0
			)
			if current == 0:
				updates["mu_max_discount_percent"] = flt(settings.max_discount_allowed)
		if updates:
			frappe.db.set_value("POS Profile", settings.pos_profile, updates, update_modified=False)


def _delete_removed_custom_fields():
	for name in REMOVED_PROFILE_FIELDS:
		if frappe.db.exists("Custom Field", name):
			frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)
