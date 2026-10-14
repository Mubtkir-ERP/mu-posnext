# Copyright (c) 2026, MUBTKIR and contributors
# For license information, please see license.txt

"""Prepaid Voucher Report.

Per-customer summary of prepaid voucher balances: units purchased, units
redeemed, remaining balance and the last redemption date. Reads the current
state from ``Prepaid Voucher Balance`` (the detailed per-transaction history
lives in the ``Prepaid Voucher Transaction`` list).
"""

import frappe
from frappe import _
from frappe.utils import cint


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{"fieldname": "customer", "label": _("Customer"), "fieldtype": "Link",
		 "options": "Customer", "width": 180},
		{"fieldname": "customer_name", "label": _("Customer Name"), "fieldtype": "Data",
		 "width": 200},
		{"fieldname": "company", "label": _("Company"), "fieldtype": "Link",
		 "options": "Company", "width": 160},
		{"fieldname": "total_purchased", "label": _("Purchased"), "fieldtype": "Int",
		 "width": 110},
		{"fieldname": "total_redeemed", "label": _("Redeemed"), "fieldtype": "Int",
		 "width": 110},
		{"fieldname": "current_balance", "label": _("Current Balance"), "fieldtype": "Int",
		 "width": 130},
		{"fieldname": "last_redeemed_on", "label": _("Last Redeemed"), "fieldtype": "Datetime",
		 "width": 170},
	]


def get_data(filters):
	conditions = []
	values = {}
	if filters.get("customer"):
		conditions.append("b.customer = %(customer)s")
		values["customer"] = filters.customer
	if filters.get("company"):
		conditions.append("b.company = %(company)s")
		values["company"] = filters.company
	if cint(filters.get("only_with_balance")):
		conditions.append("b.current_balance > 0")

	where = (" where " + " and ".join(conditions)) if conditions else ""

	return frappe.db.sql(
		f"""
		select
			b.customer,
			c.customer_name,
			b.company,
			b.total_purchased,
			b.total_redeemed,
			b.current_balance,
			b.last_redeemed_on
		from `tabPrepaid Voucher Balance` b
		left join `tabCustomer` c on c.name = b.customer
		{where}
		order by b.current_balance desc, b.customer asc
		""",
		values,
		as_dict=True,
	)
