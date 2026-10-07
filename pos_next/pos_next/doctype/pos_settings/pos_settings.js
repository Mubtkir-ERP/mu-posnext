// Copyright (c) 2024, BrainWise and contributors
// For license information, please see license.txt

frappe.ui.form.on("POS Settings", {
	refresh(frm) {
		// Only allow selectable (leaf) customer groups as the default for new customers.
		frm.set_query("default_customer_group", function () {
			return { filters: { is_group: 0 } };
		});

		// Cash disbursement can only debit a safe leaf Asset/Expense account
		// in the POS Profile company. Server validation remains authoritative.
		frm.set_query("cash_disbursement_account", function () {
			const filters = {
				is_group: 0,
				disabled: 0,
				root_type: ["in", ["Asset", "Expense"]],
				account_type: ["not in", ["Receivable", "Payable", "Cash", "Bank"]],
			};
			if (frm.doc.__company) {
				filters.company = frm.doc.__company;
			}
			return { filters };
		});

		// Set query for loyalty program filtered by POS Profile company
		frm.set_query("default_loyalty_program", function () {
			if (!frm.doc.__company) {
				return { filters: {} };
			}
			return {
				filters: {
					company: frm.doc.__company,
				},
			};
		});

		// Fetch company when form loads
		if (frm.doc.pos_profile) {
			fetch_pos_profile_company(frm);
		}
	},

	pos_profile(frm) {
		// Clear company-bound financial settings when POS Profile changes.
		frm.set_value("default_loyalty_program", "");
		frm.set_value("cash_disbursement_account", "");
		frm.doc.__company = null;

		if (frm.doc.pos_profile) {
			fetch_pos_profile_company(frm);
		}
	},
});

function fetch_pos_profile_company(frm) {
	frappe.db.get_value("POS Profile", frm.doc.pos_profile, "company", (r) => {
		if (r && r.company) {
			frm.doc.__company = r.company;
		}
	});
}
