# Copyright (c) 2026, POS Next and contributors
# License: see license.txt

"""Remove the POS Profile print-order Property Setters that created an
insert_after cycle (letter_head / tc_name moved into the custom print group,
while the standard select_print_heading sits after tc_name). The cycle broke
POS Profile meta loading and surfaced as an Internal Server Error. These two
standard fields now stay in their standard Print Settings section.
"""

import frappe

BROKEN = (
	"POS Profile-letter_head-insert_after",
	"POS Profile-tc_name-insert_after",
)


def execute():
	for name in BROKEN:
		if frappe.db.exists("Property Setter", name):
			frappe.delete_doc("Property Setter", name, ignore_permissions=True, force=True)
	frappe.clear_cache(doctype="POS Profile")
