# -*- coding: utf-8 -*-
# Copyright (c) 2026, Mubtkir and contributors
# For license information, please see license.txt

"""Restaurant paid & free item modifiers API."""

import json

import frappe
from frappe.utils import cint, flt


@frappe.whitelist()
def get_items_with_modifiers(item_codes=None):
	"""Return a list of item_codes that have modifier groups configured."""
	if not frappe.db.exists("DocType", "POS Item Modifier Group"):
		return []

	filters = {"parenttype": "Item", "parentfield": "mu_modifier_groups"}
	if item_codes:
		codes = json.loads(item_codes) if isinstance(item_codes, str) else list(item_codes)
		if codes:
			filters["parent"] = ["in", codes]

	rows = frappe.get_all("POS Item Modifier Group", filters=filters, pluck="parent", distinct=True)
	return list(rows or [])


@frappe.whitelist()
def get_item_modifiers(item_code, price_list=None):
	"""Return modifier groups and options with live Item Price for ``item_code``."""
	if not item_code or not frappe.db.exists("DocType", "POS Item Modifier Group"):
		return []

	group_links = frappe.get_all(
		"POS Item Modifier Group",
		filters={"parent": item_code, "parenttype": "Item", "parentfield": "mu_modifier_groups"},
		fields=["modifier_group"],
		order_by="idx asc",
	)
	if not group_links:
		return []

	result = []
	for gl in group_links:
		grp_name = gl.get("modifier_group")
		if not grp_name or not frappe.db.exists("POS Modifier Group", grp_name):
			continue
		grp = frappe.get_doc("POS Modifier Group", grp_name)
		options_out = []
		for opt in grp.get("options") or []:
			opt_type = opt.option_type or "Paid Item"
			price = 0.0
			item_name = opt.label
			if opt_type == "Paid Item" and opt.item_code:
				price = _get_live_item_price(opt.item_code, price_list)
				item_name = opt.label or frappe.db.get_value("Item", opt.item_code, "item_name") or opt.item_code
			options_out.append({
				"name": opt.name,
				"option_type": opt_type,
				"item_code": opt.item_code or "",
				"label": item_name,
				"price": flt(price),
				"is_default": cint(opt.is_default),
			})
		if options_out:
			result.append({
				"name": grp.name,
				"group_name": grp.group_name,
				"selection_type": grp.selection_type or "Multiple",
				"is_required": cint(grp.is_required),
				"options": options_out,
			})
	return result


def _get_live_item_price(item_code, price_list=None):
	"""Fetch selling price from Item Price for ``price_list`` or fallback to standard_rate."""
	if price_list:
		rate = frappe.db.get_value(
			"Item Price",
			{"item_code": item_code, "price_list": price_list, "selling": 1},
			"price_list_rate",
		)
		if rate is not None:
			return flt(rate)

	rate = frappe.db.get_value(
		"Item Price",
		{"item_code": item_code, "selling": 1},
		"price_list_rate",
	)
	if rate is not None:
		return flt(rate)

	return flt(frappe.db.get_value("Item", item_code, "standard_rate") or 0)
