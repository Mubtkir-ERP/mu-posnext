frappe.ui.form.on("Address", {
	refresh(frm) {
		if (frm.is_new()) return;

		// Check if address is linked to a customer
		const customer_link = (frm.doc.links || []).find(l => l.link_doctype === "Customer");
		if (!customer_link || !customer_link.link_name) return;

		frm.add_custom_button(__("Print Branch QR Card"), () => {
			frappe.call({
				method: "pos_next.operations.customer_branches.get_branch_qr_card_html",
				args: {
					customer: customer_link.link_name,
					address_name: frm.doc.name
				},
				callback(resp) {
					if (resp.message) {
						const w = window.open("", "_blank");
						w.document.open();
						w.document.write(resp.message);
						w.document.close();
					}
				}
			});
		}, __("Actions"));
	}
});
