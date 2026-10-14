# Copyright (c) 2026, POS Next and contributors
# License: see license.txt

"""Second settings-reorg pass:

1. POS Settings -> POS Profile: move kitchen-printer rows (POS Kitchen Printer)
   from each POS Settings record to its POS Profile (field mu_kitchen_printers).
2. Drop the cash-disbursement fields removed from POS Settings
   (allow_cash_disbursement, cash_disbursement_account). The operational cash
   policy already lives on the POS Profile (mu_allow_cash_expense + account).
"""

import frappe


REMOVED_PROFILE_FIELDS = (
	"POS Profile-mu_posnext_tab",
	"POS Profile-mu_posnext_sales_section",
	"POS Profile-mu_sales_col_right",
)


def execute():
	_move_kitchen_printers()
	_drop_removed_settings_columns()
	_delete_old_profile_layout_fields()


def _delete_old_profile_layout_fields():
	# The branch tab and the sale-policy section wrapper were removed; their
	# fields now live inside the standard Details tab / Configuration section.
	for name in REMOVED_PROFILE_FIELDS:
		if frappe.db.exists("Custom Field", name):
			frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)


def _move_kitchen_printers():
	if not frappe.db.table_exists("POS Kitchen Printer"):
		return

	rows = frappe.get_all(
		"POS Kitchen Printer",
		filters={"parenttype": "POS Settings"},
		fields=["name", "parent"],
	)
	if not rows:
		return

	# Map each POS Settings record to its POS Profile.
	settings_to_profile = {}
	for s in frappe.get_all("POS Settings", fields=["name", "pos_profile"]):
		settings_to_profile[s.name] = s.pos_profile

	for row in rows:
		profile = settings_to_profile.get(row.parent)
		if not profile or not frappe.db.exists("POS Profile", profile):
			continue
		frappe.db.set_value(
			"POS Kitchen Printer",
			row.name,
			{
				"parent": profile,
				"parenttype": "POS Profile",
				"parentfield": "mu_kitchen_printers",
			},
			update_modified=False,
		)


def _drop_removed_settings_columns():
	for col in ("allow_cash_disbursement", "cash_disbursement_account"):
		if frappe.db.has_column("POS Settings", col):
			try:
				frappe.db.sql_ddl(f"ALTER TABLE `tabPOS Settings` DROP COLUMN `{col}`")
			except Exception:
				frappe.log_error(frappe.get_traceback(), f"Drop POS Settings.{col}")
