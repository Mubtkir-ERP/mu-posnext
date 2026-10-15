# Copyright (c) 2026, MUBTKIR and contributors
# For license information, please see license.txt
#
# يضيف جدول موازنات مدى داخل POS Closing Shift كحقول مخصّصة (قابلة للفصل لاحقًا).

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    if not frappe.db.exists("DocType", "Mada Shift Settlement"):
        return

    create_custom_fields(
        {
            "POS Closing Shift": [
                {
                    "fieldname": "mu_mada_section",
                    "label": "Mada Settlements",
                    "fieldtype": "Section Break",
                    "insert_after": "payment_reconciliation",
                    "collapsible": 1,
                },
                {
                    "fieldname": "mu_mada_settlements",
                    "label": "Mada Settlements",
                    "fieldtype": "Table",
                    "options": "Mada Shift Settlement",
                    "insert_after": "mu_mada_section",
                },
            ]
        },
        ignore_validate=True,
    )
    frappe.clear_cache(doctype="POS Closing Shift")
