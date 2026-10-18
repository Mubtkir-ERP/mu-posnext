# -*- coding: utf-8 -*-
# Copyright (c) 2026, POS Next and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {
            "label": _("Closing Shift"),
            "fieldname": "closing_shift",
            "fieldtype": "Link",
            "options": "POS Closing Shift",
            "width": 180
        },
        {
            "label": _("Posting Date"),
            "fieldname": "posting_date",
            "fieldtype": "Date",
            "width": 110
        },
        {
            "label": _("POS Profile"),
            "fieldname": "pos_profile",
            "fieldtype": "Link",
            "options": "POS Profile",
            "width": 150
        },
        {
            "label": _("Cashier / Driver"),
            "fieldname": "user",
            "fieldtype": "Link",
            "options": "User",
            "width": 150
        },
        {
            "label": _("Non-Taxable Amount (Delivery/Dafour)"),
            "fieldname": "non_taxable_amount",
            "fieldtype": "Currency",
            "width": 180
        },
        {
            "label": _("Cash Sweep Entry"),
            "fieldname": "cash_sweep_entry",
            "fieldtype": "Link",
            "options": "Journal Entry",
            "width": 160
        },
        {
            "label": _("Remarks"),
            "fieldname": "remarks",
            "fieldtype": "Data",
            "width": 220
        }
    ]


def get_data(filters):
    conditions = []
    values = {}

    if filters:
        if filters.get("pos_profile"):
            conditions.append("cs.pos_profile = %(pos_profile)s")
            values["pos_profile"] = filters["pos_profile"]
        if filters.get("user"):
            conditions.append("cs.user = %(user)s")
            values["user"] = filters["user"]
        if filters.get("from_date") and filters.get("to_date"):
            conditions.append("cs.posting_date BETWEEN %(from_date)s AND %(to_date)s")
            values["from_date"] = filters["from_date"]
            values["to_date"] = filters["to_date"]

    where_clause = " AND ".join(conditions)
    if where_clause:
        where_clause = " AND " + where_clause

    query = f"""
        SELECT 
            cs.name as closing_shift,
            cs.posting_date,
            cs.pos_profile,
            cs.user,
            cs.mu_non_taxable_amount as non_taxable_amount,
            cs.mu_cash_sweep_entry as cash_sweep_entry,
            cs.mu_non_taxable_remarks as remarks
        FROM `tabPOS Closing Shift` cs
        WHERE cs.docstatus = 1 AND IFNULL(cs.mu_non_taxable_amount, 0) > 0 {where_clause}
        ORDER BY cs.posting_date DESC, cs.creation DESC
    """

    return frappe.db.sql(query, values, as_dict=True)
