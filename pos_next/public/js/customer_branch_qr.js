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
						<div class="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-3 p-3 border rounded-lg mb-2 bg-gray-50 hover:bg-blue-50">
							<div class="min-w-0">
								<div class="font-bold text-sm text-gray-800 break-words">🏢 ${b.branch_title}</div>
								<div class="text-xs text-gray-500 break-words">${b.address_line1 || ""} ${b.city || ""} ${b.phone ? " | " + b.phone : ""}</div>
							</div>
							<div class="flex flex-wrap items-center justify-end gap-2 w-full sm:w-auto">
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
										<div class="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-2 mb-3">
											<p class="text-xs text-muted mb-0">${__("Select a branch or print/send the customer QR card:")}</p>
											<div class="flex flex-wrap items-center gap-2">
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

			const showVoucher = Boolean(data.has_voucher_activity || Number(data.voucher_balance || 0) > 0);
			const voucherBoxHtml = showVoucher ? `
				<div style="margin: 10px 0; padding: 8px; border-radius: 10px; background: #ecfdf5; border: 1px solid #a7f3d0;">
					<div style="font-size: 11px; color: #047857; font-weight: 700;">🎟️ ${__("Voucher Balance")}</div>
					<div style="font-size: 22px; color: #065f46; font-weight: 900;">${data.voucher_balance || 0}</div>
				</div>
			` : "";

			let d = new frappe.ui.Dialog({
				title: __("Customer QR Card") + " - " + (data.branch_title || data.customer_name || data.customer),
				fields: [
					{
						fieldtype: "HTML",
						fieldname: "qr_card_html",
						options: `
							<div class="text-center p-3 border rounded bg-white shadow-sm" style="max-width: 100%; width: 360px; margin: 0 auto; direction: rtl;">
								${data.company_name ? `<div style="font-size: 15px; font-weight: 800; color: #0f172a; margin-bottom: 4px;">${data.company_name}</div>` : ""}
								${displayTitle}
								${(data.address_line1 || data.city) ? `<div style="font-size: 11px; color: #64748b; margin-top: 2px;">📍 ${data.address_line1 || ""} ${data.city || ""}</div>` : ""}

								${voucherBoxHtml}

								<div style="display:flex; justify-content:center; align-items:center; margin: 12px 0; background: #fafafa; padding: 12px; border-radius: 12px; border: 1px solid #e2e8f0;">
									<img src="${data.qr_image}" alt="QR" style="width: 190px; height: 190px; max-width: 100%; object-fit: contain;" />
								</div>

								<div class="flex flex-col gap-2" style="gap: 8px;">
									<button type="button" class="btn btn-success btn-block btn-send-wa" style="font-weight: 700;">
										💬 ${__("Send via WhatsApp")} ${data.mobile_no ? `(${data.mobile_no})` : ""}
									</button>
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
	const esc = (v) => (frappe?.utils?.escape_html ? frappe.utils.escape_html(String(v || "")) : String(v || ""));
	const companyName = esc(data.company_name);
	const customerName = esc(data.customer_name || data.customer || data.branch_title);
	const branchTitle = esc(data.branch_title);
	const branchHtml = branchTitle && branchTitle !== customerName
		? `<div class="branch-name">🏢 ${branchTitle}</div>`
		: "";

	const printHtml = `<!DOCTYPE html>
		<html dir="rtl" lang="ar">
			<head>
				<meta charset="utf-8">
				<title>QR Card</title>
				<style>
					@page { size: A6 portrait; margin: 0; }
					* { box-sizing: border-box; }
					html, body { margin: 0; padding: 0; width: 105mm; height: 148mm; font-family: sans-serif; direction: rtl; background: #fff; }
					.a6-sticker { width: 105mm; height: 148mm; padding: 5mm; page-break-after: always; display: flex; }
					.a6-sticker:last-child { page-break-after: auto; }
					.a6-card { width: 100%; height: 100%; border: 4px solid #F28C28; border-radius: 14px; padding: 7mm 5mm; display: flex; flex-direction: column; align-items: center; text-align: center; justify-content: space-between; overflow: hidden; }
					.company-name { font-size: 20px; font-weight: 900; color: #111827; margin-bottom: 10px; }
					.customer-name { font-size: 23px; font-weight: 800; color: #111827; margin: 6px 0; }
					.branch-name { font-size: 16px; font-weight: 700; color: #334155; margin: 4px 0; }
					.qr-box { width: 82mm; height: 82mm; display: flex; align-items: center; justify-content: center; margin: auto; }
					.qr-box img { width: 100%; height: 100%; object-fit: contain; }
					.a6-footer { width: 100%; text-align: center; font-size: 9px; font-weight: 600; color: #999999; padding-top: 5px; }
				</style>
			</head>
			<body>
				<div class="a6-sticker">
					<div class="a6-card">
						<div style="width:100%;">
							${companyName ? `<div class="company-name">${companyName}</div>` : ""}
							<div class="customer-name">${customerName}</div>
							${branchHtml}
						</div>
						<div class="qr-box"><img src="${data.qr_image}" alt="Customer QR Code" /></div>
						<div class="a6-footer">Powered By MUBTKIR ERP</div>
					</div>
				</div>
			</body>
		</html>`;
	const w = window.open("", "_blank", "width=450,height=650");
	w.document.open();
	w.document.write(printHtml);
	w.document.close();
	w.focus();
	setTimeout(() => { w.print(); }, 400);
}
