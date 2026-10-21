frappe.ui.form.on("Customer", {
	refresh(frm) {
		if (frm.is_new()) return;

		frm.add_custom_button(__("Print Branch QR Codes"), () => {
			frappe.call({
				method: "pos_next.operations.customer_branches.get_customer_branches",
				args: { customer: frm.doc.name },
				callback(r) {
					const branches = r.message || [];
					if (branches.length === 0) {
						frappe.msgprint(__("No linked addresses/branches found for this customer. Please add an address first."));
						return;
					}

					let options_html = branches.map(b => `
						<div class="flex justify-between items-center p-3 border rounded-lg mb-2 bg-gray-50 hover:bg-blue-50">
							<div>
								<div class="font-bold text-sm text-gray-800">🏢 ${b.branch_title}</div>
								<div class="text-xs text-gray-500">${b.address_line1 || ""} ${b.city || ""} ${b.phone ? " | " + b.phone : ""}</div>
							</div>
							<div class="flex items-center gap-2">
								<img src="${b.qr_image}" class="w-12 h-12 border rounded bg-white p-0.5" />
								<button class="btn btn-sm btn-primary btn-print-qr" data-address="${b.address_name}">
									${__("Print QR Card")}
								</button>
							</div>
						</div>
					`).join("");

					let d = new frappe.ui.Dialog({
						title: __("Customer Branches QR Codes") + " - " + frm.doc.customer_name,
						size: "large",
						fields: [
							{
								fieldtype: "HTML",
								fieldname: "branches_html",
								options: `
									<div class="p-2">
										<p class="text-xs text-muted mb-3">${__("Select a branch to view and print its POS quick-scan QR card:")}</p>
										${options_html}
									</div>
								`
							}
						]
					});

					d.$wrapper.find(".btn-print-qr").on("click", function() {
						const address_name = $(this).attr("data-address");
						frappe.call({
							method: "pos_next.operations.customer_branches.get_branch_qr_card_html",
							args: { customer: frm.doc.name, address_name: address_name },
							callback(resp) {
								if (resp.message) {
									const w = window.open("", "_blank");
									w.document.open();
									w.document.write(resp.message);
									w.document.close();
								}
							}
						});
					});

					d.show();
				}
			});
		}, __("Actions"));
	}
});
