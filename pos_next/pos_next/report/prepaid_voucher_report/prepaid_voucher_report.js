// Copyright (c) 2026, MUBTKIR and contributors
// For license information, please see license.txt

frappe.query_reports["Prepaid Voucher Report"] = {
	filters: [
		{
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			options: "Customer",
		},
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "only_with_balance",
			label: __("Only With Balance"),
			fieldtype: "Check",
			default: 1,
		},
	],
};
