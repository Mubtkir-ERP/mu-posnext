# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	"""Return columns for the report"""
	return [
		{
			"fieldname": "shift",
			"label": _("Shift"),
			"fieldtype": "Link",
			"options": "POS Closing Shift",
			"width": 150
		},
		{
			"fieldname": "pos_profile",
			"label": _("POS Profile"),
			"fieldtype": "Link",
			"options": "POS Profile",
			"width": 150
		},
		{
			"fieldname": "cashier",
			"label": _("Cashier"),
			"fieldtype": "Link",
			"options": "User",
			"width": 150
		},
		{
			"fieldname": "period_start_date",
			"label": _("Shift Start"),
			"fieldtype": "Datetime",
			"width": 150
		},
		{
			"fieldname": "period_end_date",
			"label": _("Shift End"),
			"fieldtype": "Datetime",
			"width": 150
		},
		{
			"fieldname": "total_sales",
			"label": _("Total Sales"),
			"fieldtype": "Currency",
			"width": 130
		},
		{
			"fieldname": "invoice_count",
			"label": _("Invoice Count"),
			"fieldtype": "Int",
			"width": 110
		},
		{
			"fieldname": "average_ticket_size",
			"label": _("Avg Ticket Size"),
			"fieldtype": "Currency",
			"width": 130
		},
		{
			"fieldname": "total_discounts",
			"label": _("Total Discounts"),
			"fieldtype": "Currency",
			"width": 130
		},
		{
			"fieldname": "discount_percentage",
			"label": _("Discount %"),
			"fieldtype": "Percent",
			"width": 100
		},
		{
			"fieldname": "return_count",
			"label": _("Returns"),
			"fieldtype": "Int",
			"width": 90
		},
		{
			"fieldname": "return_amount",
			"label": _("Return Amount"),
			"fieldtype": "Currency",
			"width": 130
		},
		{
			"fieldname": "net_sales",
			"label": _("Net Sales"),
			"fieldtype": "Currency",
			"width": 130
		},
		{
			"fieldname": "efficiency_score",
			"label": _("Efficiency Score"),
			"fieldtype": "Percent",
			"width": 120
		}
	]


def get_data(filters):
	"""Get report data based on filters"""
	conditions = get_conditions(filters)

	query = """
		SELECT
			pcs.name as shift,
			pcs.pos_profile,
			pcs.user as cashier,
			pcs.period_start_date,
			pcs.period_end_date,
			COALESCE(SUM(CASE WHEN si.is_return = 0 THEN si.grand_total ELSE 0 END), 0) as total_sales,
			COUNT(CASE WHEN si.is_return = 0 THEN si.name END) as invoice_count,
			COALESCE(SUM(CASE WHEN si.is_return = 0 THEN si.discount_amount ELSE 0 END), 0) as total_discounts,
			COUNT(CASE WHEN si.is_return = 1 THEN si.name END) as return_count,
			COALESCE(SUM(CASE WHEN si.is_return = 1 THEN ABS(si.grand_total) ELSE 0 END), 0) as return_amount
		FROM `tabPOS Closing Shift` pcs
		LEFT JOIN `tabSales Invoice` si ON (
			(si.posa_pos_opening_shift = pcs.pos_opening_shift)
			OR (
				si.pos_profile = pcs.pos_profile
				AND si.owner = pcs.user
				AND si.posting_date >= DATE(pcs.period_start_date)
				AND si.posting_date <= DATE(pcs.period_end_date)
			)
		)
		AND si.docstatus = 1
		AND si.is_pos = 1
		WHERE pcs.docstatus = 1
		{conditions}
		GROUP BY pcs.name, pcs.pos_profile, pcs.user, pcs.period_start_date, pcs.period_end_date
		ORDER BY pcs.period_start_date DESC
	""".format(conditions=conditions)

	data = frappe.db.sql(query, filters, as_dict=1)

	# Calculate derived fields
	for row in data:
		# Average ticket size
		if row.invoice_count > 0:
			row.average_ticket_size = flt(row.total_sales / row.invoice_count, 2)
		else:
			row.average_ticket_size = 0

		# Discount percentage
		if row.total_sales > 0:
			row.discount_percentage = flt((row.total_discounts / row.total_sales) * 100, 2)
		else:
			row.discount_percentage = 0

		# Net sales (sales minus returns)
		row.net_sales = flt(row.total_sales - row.return_amount, 2)

		# Efficiency score (based on sales volume, low returns, and reasonable discounts)
		base_efficiency = 100

		# Penalize for returns (returns > 10% of sales reduces efficiency)
		if row.total_sales > 0:
			return_ratio = (row.return_amount / row.total_sales) * 100
			if return_ratio > 10:
				base_efficiency -= (return_ratio - 10) * 2  # Deduct 2% for each % above 10%

		# Penalize for excessive discounts (discounts > 15% reduces efficiency)
		if row.discount_percentage > 15:
			base_efficiency -= (row.discount_percentage - 15)  # Deduct 1% for each % above 15%

		# Bonus for high ticket size (if avg ticket > 1000, add bonus)
		if row.average_ticket_size > 1000:
			base_efficiency += min((row.average_ticket_size / 1000) * 2, 10)  # Max 10% bonus

		row.efficiency_score = max(0, min(100, flt(base_efficiency, 2)))  # Cap between 0-100

	return data


def get_conditions(filters):
	"""Build WHERE conditions from filters"""
	conditions = []

	if filters.get("from_date"):
		conditions.append("pcs.period_start_date >= %(from_date)s")

	if filters.get("to_date"):
		conditions.append("pcs.period_end_date <= %(to_date)s")

	if filters.get("pos_profile"):
		conditions.append("pcs.pos_profile = %(pos_profile)s")

	if filters.get("cashier"):
		conditions.append("pcs.user = %(cashier)s")

	if filters.get("shift"):
		conditions.append("pcs.name = %(shift)s")

	return "AND " + " AND ".join(conditions) if conditions else ""
