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
	"mu_hide_delivery_prices",
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
	"mu_allow_a4_print",
	"mu_network_printer_ip",
	"mu_network_printer_port",
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

	# Also remove any legacy Section Breaks whose fieldname differed on older sites
	legacy_section_labels = (
		"Print Formats",
		"قوالب طباعة الفواتير",
		"Invoice Communications",
		"إرسال الفواتير",
		"Prepaid Voucher System",
		"نظام القسائم المسبقة",
	)
	for cf_name in frappe.get_all(
		"Custom Field",
		filters={"dt": "POS Profile", "fieldtype": "Section Break", "label": ["in", legacy_section_labels]},
		pluck="name",
	):
		frappe.delete_doc("Custom Field", cf_name, ignore_permissions=True, force=True)

	for fieldname in SETTINGS_TO_PROFILE_FIELDS:
		if frappe.db.has_column("POS Settings", fieldname):
			frappe.db.sql_ddl(f"ALTER TABLE `tabPOS Settings` DROP COLUMN `{fieldname}`")


def _migrate_kitchen_printers():
	"""Create POS Printer records for legacy kitchen printer rows and drop redundant columns."""
	if not frappe.db.exists("DocType", "POS Printer"):
		return
	legacy_cols = ("printer_name", "printer_ip", "printer_port")
	has_legacy = any(frappe.db.has_column("POS Kitchen Printer", c) for c in legacy_cols)
	if not has_legacy:
		return

	select_cols = ["name"] + [c for c in ("printer",) + legacy_cols if frappe.db.has_column("POS Kitchen Printer", c)]
	rows = frappe.get_all("POS Kitchen Printer", fields=select_cols)
	for r in rows:
		if r.get("printer"):
			continue
		p_name = (r.get("printer_name") or "").strip()
		p_ip = (r.get("printer_ip") or "").strip()
		if not p_name and not p_ip:
			continue
		label = p_name or p_ip
		existing = frappe.db.get_value("POS Printer", {"printer_name": label}, "name")
		if not existing:
			doc = frappe.new_doc("POS Printer")
			doc.printer_name = label
			doc.ip_address = p_ip
			doc.port = cint(r.get("printer_port")) or 9100
			doc.insert(ignore_permissions=True)
			existing = doc.name
		frappe.db.set_value("POS Kitchen Printer", r.name, "printer", existing, update_modified=False)

	for col in legacy_cols:
		if frappe.db.has_column("POS Kitchen Printer", col):
			frappe.db.sql_ddl(f"ALTER TABLE `tabPOS Kitchen Printer` DROP COLUMN `{col}`")

	if frappe.db.has_column("POS Profile", "mu_network_printer_ip") and frappe.db.has_column("POS Profile", "mu_cashier_printer"):
		profiles = frappe.get_all("POS Profile", fields=["name", "mu_network_printer_ip", "mu_network_printer_port", "mu_cashier_printer"])
		for prof in profiles:
			ip = (prof.get("mu_network_printer_ip") or "").strip()
			if ip and not prof.get("mu_cashier_printer"):
				existing = frappe.db.get_value("POS Printer", {"ip_address": ip}, "name")
				if not existing:
					doc = frappe.new_doc("POS Printer")
					doc.printer_name = f"Cashier - {prof.name}"
					doc.ip_address = ip
					doc.port = cint(prof.get("mu_network_printer_port")) or 9100
					doc.insert(ignore_permissions=True)
					existing = doc.name
				frappe.db.set_value("POS Profile", prof.name, "mu_cashier_printer", existing, update_modified=False)


def execute():
	_migrate_voucher_values()
	_migrate_kitchen_printers()
	_drop_obsolete_custom_fields()
	if frappe.db.exists("Property Setter", "POS Profile-section_break_23-label"):
		frappe.delete_doc("Property Setter", "POS Profile-section_break_23-label", ignore_permissions=True, force=True)
	frappe.clear_cache(doctype="POS Profile")
	frappe.clear_cache(doctype="POS Settings")
	frappe.clear_cache(doctype="POS Kitchen Printer")
