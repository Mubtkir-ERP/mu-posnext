frappe.ui.form.on("Customer", {
	refresh(frm) {
		if (frm.is_new()) return;

		// Remove any legacy duplicate QR buttons so only one unified button appears
		frm.remove_custom_button(__("Print Branch QR Codes"));
		frm.remove_custom_button("رمز QR لتسليم الغاز 🏷️");
		frm.remove_custom_button("رمز QR لتسليم الغاز 🏷️", "الغاز");

		frm.add_custom_button(__("Customer QR Card"), () => {
			frappe.call({
				method: "pos_next.operations.customer_branches.get_customer_branches",
				args: { customer: frm.doc.name },
				freeze: true,
				freeze_message: __("Loading QR Card..."),
				callback(r) {
					const branches = r.message || [];
					if (branches.length === 0) {
						open_single_customer_qr_modal(frm.doc.name, null);
						return;
					}

					let options_html = branches.map(b => `
						<div class="flex justify-between items-center p-3 border rounded-lg mb-2 bg-gray-50 hover:bg-blue-50">
							<div>
								<div class="font-bold text-sm text-gray-800">🏢 ${b.branch_title}</div>
								<div class="text-xs text-gray-500">${b.address_line1 || ""} ${b.city || ""} ${b.phone ? " | " + b.phone : ""}</div>
							</div>
							<div class="flex items-center gap-2">
								<img src="${b.qr_image}" alt="QR" style="width: 48px; height: 48px; min-width: 48px; object-fit: contain; background: white; border: 1px solid #e2e8f0; border-radius: 6px; padding: 2px;" />
								<button class="btn btn-xs btn-success btn-whatsapp-branch" data-address="${b.address_name}" title="${__("Send via WhatsApp")}">
									💬 ${__("WhatsApp")}
								</button>
								<button class="btn btn-xs btn-primary btn-preview-branch" data-address="${b.address_name}">
									🏷️ ${__("Card / Print")}
								</button>
							</div>
						</div>
					`).join("");

					let d = new frappe.ui.Dialog({
						title: __("Customer QR Card") + " - " + (frm.doc.customer_name || frm.doc.name),
						size: "large",
						fields: [
							{
								fieldtype: "HTML",
								fieldname: "branches_html",
								options: `
									<div class="p-2">
										<div class="flex flex-wrap justify-between items-center gap-2 mb-3">
											<p class="text-xs text-muted mb-0">${__("Select a branch or print/send the customer QR card:")}</p>
											<div class="flex items-center gap-2">
												<button class="btn btn-sm btn-success btn-whatsapp-main">
													💬 ${__("Send Main Card (WhatsApp)")}
												</button>
												<button class="btn btn-sm btn-secondary btn-print-all-qr">
													🖨️ ${__("Print All Branch Cards")}
												</button>
											</div>
										</div>
										${options_html}
									</div>
								`
							}
						]
					});

					d.$wrapper.find(".btn-preview-branch").on("click", function() {
						const address_name = $(this).attr("data-address");
						open_single_customer_qr_modal(frm.doc.name, address_name);
					});

					d.$wrapper.find(".btn-whatsapp-branch").on("click", function() {
						const address_name = $(this).attr("data-address");
						send_qr_whatsapp(frm.doc.name, address_name);
					});

					d.$wrapper.find(".btn-whatsapp-main").on("click", function() {
						send_qr_whatsapp(frm.doc.name, null);
					});

					d.$wrapper.find(".btn-print-all-qr").on("click", function() {
						frappe.call({
							method: "pos_next.operations.customer_branches.get_all_branches_qr_cards_html",
							args: { customer: frm.doc.name },
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
		});
	}
});

function open_single_customer_qr_modal(customer, address_name) {
	frappe.call({
		method: "pos_next.operations.customer_branches.get_customer_qr_card_data",
		args: { customer: customer, address_name: address_name || "" },
		freeze: true,
		freeze_message: __("Loading QR Card..."),
		callback(r) {
			if (!r.message) return;
			const data = r.message;
			const displayTitle = data.branch_title
				? `<div style="font-size: 15px; font-weight: 800; color: #0f172a; margin-top: 2px;">🏢 ${data.branch_title}</div>`
				: `<div style="font-size: 16px; font-weight: 800; color: #0f172a;">${data.customer_name || data.customer}</div>`;

			let d = new frappe.ui.Dialog({
				title: __("Customer QR Card") + " - " + (data.branch_title || data.customer_name || data.customer),
				fields: [
					{
						fieldtype: "HTML",
						fieldname: "qr_card_html",
						options: `
							<div class="text-center p-3 border rounded bg-white shadow-sm" style="max-width: 360px; margin: 0 auto; direction: rtl;">
								${data.company_name ? `<div style="font-size: 15px; font-weight: 800; color: #0f172a; margin-bottom: 4px;">${data.company_name}</div>` : ""}
								${displayTitle}
								${(data.address_line1 || data.city) ? `<div style="font-size: 11px; color: #64748b; margin-top: 2px;">📍 ${data.address_line1 || ""} ${data.city || ""}</div>` : ""}

								<div style="margin: 10px 0; padding: 8px; border-radius: 10px; background: #ecfdf5; border: 1px solid #a7f3d0;">
									<div style="font-size: 11px; color: #047857; font-weight: 700;">🎟️ ${__("Voucher Balance")}</div>
									<div style="font-size: 22px; color: #065f46; font-weight: 900;">${data.voucher_balance || 0}</div>
								</div>

								<div style="display:flex; justify-content:center; align-items:center; margin: 12px 0; background: #fafafa; padding: 12px; border-radius: 12px; border: 1px solid #e2e8f0;">
									<img src="${data.qr_image}" alt="QR" style="width: 190px; height: 190px; object-fit: contain;" />
								</div>

								<div class="flex flex-col gap-2" style="gap: 8px;">
									<button type="button" class="btn btn-success btn-block btn-send-wa" style="font-weight: 700;">
										💬 ${__("Send via WhatsApp")} ${data.mobile_no ? `(${data.mobile_no})` : ""}
									</button>
									<a href="${data.card_url}" target="_blank" class="btn btn-default btn-block" style="font-weight: 600;">
										🔗 ${__("Open Digital Balance Page")}
									</a>
								</div>

								<div style="font-size: 11px; color: #64748b; text-align: center; margin-top: 10px; font-weight: 600;">Powered By Mubtkir ERP</div>
							</div>
						`
					}
				],
				primary_action_label: __("Print A6 Sticker 🖨️"),
				primary_action() {
					print_a6_customer_qr_sticker(data);
				}
			});

			d.$wrapper.find(".btn-send-wa").on("click", function() {
				send_qr_whatsapp(customer, address_name);
			});

			d.show();
		}
	});
}

function send_qr_whatsapp(customer, address_name) {
	frappe.call({
		method: "pos_next.operations.customer_branches.send_customer_qr_whatsapp",
		args: { customer: customer, address_name: address_name || "" },
		freeze: true,
		freeze_message: __("Sending WhatsApp message..."),
		callback(r) {
			if (r.message && r.message.sent) {
				frappe.show_alert({
					message: __("QR Card sent via WhatsApp to {0}", [r.message.mobile_no]),
					indicator: "green"
				});
			}
		}
	});
}

function print_a6_customer_qr_sticker(data) {
	const titleHtml = data.branch_title
		? `<h2 style="margin: 6px 0; font-size: 20px; color: #0f172a;">🏢 ${data.branch_title}</h2>`
		: `<h2 style="margin: 6px 0; font-size: 22px; color: #0f172a;">${data.customer_name || data.customer}</h2>`;

	const printHtml = `
		<html>
			<head>
				<title>QR Card</title>
				<style>
					@page { size: A6 portrait; margin: 0; }
					* { box-sizing: border-box; }
					body { margin: 0; padding: 0; font-family: sans-serif; direction: rtl; width: 105mm; height: 148mm; }
					.a6-sticker { width: 105mm; height: 148mm; padding: 6mm; display: flex; align-items: stretch; justify-content: center; }
					.a6-card { width: 100%; border: 2px solid #0f172a; border-radius: 10px; padding: 6mm; display: flex; flex-direction: column; justify-content: space-between; align-items: center; text-align: center; }
					.company-name { font-size: 16px; font-weight: 800; color: #0f172a; margin-bottom: 4px; }
					.subtitle { font-size: 13px; font-weight: 700; color: #0284c7; margin: 0 0 4px 0; }
					.address-line { margin: 4px 0 0 0; font-size: 12px; color: #64748b; }
					.qr-box { width: 62mm; height: 62mm; display: flex; align-items: center; justify-content: center; margin: 4mm auto; }
					.qr-box img { width: 100%; height: 100%; object-fit: contain; }
					.a6-footer { width: 100%; text-align: center; font-size: 11px; font-weight: 600; color: #475569; padding-top: 4px; border-top: 1px dashed #cbd5e1; }
				</style>
			</head>
			<body>
				<div class="a6-sticker">
					<div class="a6-card">
						<div>
							${data.company_name ? `<div class="company-name">${data.company_name}</div>` : ""}
							<div class="subtitle">${__("Customer QR Card")}</div>
							${titleHtml}
							${(data.address_line1 || data.city) ? `<p class="address-line">📍 ${data.address_line1 || ""} ${data.city || ""}</p>` : ""}
						</div>
						<div class="qr-box"><img src="${data.qr_image}" alt="QR" /></div>
						<div class="a6-footer">Powered By Mubtkir ERP</div>
					</div>
				</div>
			</body>
		</html>
	`;
	const w = window.open("", "_blank", "width=450,height=650");
	w.document.open();
	w.document.write(printHtml);
	w.document.close();
	w.focus();
	setTimeout(() => { w.print(); }, 400);
}
