# Copyright (c) 2026, Mubtkir and contributors
# For license information, please see license.txt

"""Final consolidated cleanup of legacy POS Profile sections, duplicate fields, and printers."""

import frappe

from pos_next.patches.v1_25_17.cleanup_duplicate_settings_and_merge_print import execute as run_cleanup


def execute():
	for ps_name in ("POS Profile-section_break_19-label", "POS Profile-section_break_23-label"):
		if frappe.db.exists("Property Setter", ps_name):
			frappe.delete_doc("Property Setter", ps_name, ignore_permissions=True, force=True)
	run_cleanup()
