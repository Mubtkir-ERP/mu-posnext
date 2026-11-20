import { call } from "@/utils/apiWrapper"
import { logger } from "@/utils/logger"
import { printHTML as qzPrintHTML } from "@/utils/qzTray"

const log = logger.create("PrintInvoice")

// Printing must be configured on the active POS Profile; no internal template fallback.
const missingFormat = () => new Error("Configure the invoice Print Format in POS Profile before printing")

// ============================================================================
// Shared helpers
// ============================================================================

function formatCurrency(amount) {
	return Number.parseFloat(amount || 0).toFixed(2)
}

/**
 * Resolve print format & letterhead from a POS Profile.
 * Fails explicitly when the profile has no configured template.
 */
async function resolvePrintSettings(posProfile, printFormat, letterhead, paper = "thermal") {
	if (printFormat && paper === "thermal") return { printFormat, letterhead }

	if (posProfile) {
		try {
			const doc = await call("frappe.client.get", {
				doctype: "POS Profile",
				name: posProfile,
			})
			if (doc) {
				const selected = paper === "a4" ? doc.mu_a4_print_format : (doc.mu_thermal_print_format || doc.print_format)
				if (!selected) {
					throw paper === "a4"
						? new Error("A4 printing is disabled for this POS Profile")
						: missingFormat()
				}
				return { printFormat: selected, letterhead: letterhead || doc.letter_head || null }
			}
		} catch (err) {
			log.warn("Could not fetch POS Profile print settings:", err)
			throw err
		}
	}

	throw missingFormat()
}

// ============================================================================
// Browser printing (opens /printview in a new window)
// ============================================================================

/**
 * Open Frappe's /printview in a new browser window.
 * The page includes trigger_print=1 so the OS print dialog appears automatically.
 * Never renders an internal receipt template as fallback.
 */
export async function printInvoice(invoiceData, printFormat = null, letterhead = null) {
	try {
		if (!invoiceData?.name) throw new Error("Invalid invoice data")

		const doctype = invoiceData.doctype || "Sales Invoice"
		const format = printFormat || (await resolvePrintSettings(invoiceData.pos_profile || invoiceData.posProfile, null, letterhead)).printFormat

		const params = new URLSearchParams({
			doctype,
			name: invoiceData.name,
			format,
			no_letterhead: letterhead ? 0 : 1,
			_lang: "en",
			trigger_print: 1,
			_t: Date.now(),
		})
		if (letterhead) params.append("letterhead", letterhead)

		const printWindow = window.open(`/printview?${params}`, "_blank", "width=800,height=600")
		if (!printWindow) {
			throw new Error("Popup blocked — check your browser settings.")
		}
		return true
	} catch (error) {
		log.error("Browser print failed:", error)
		throw error
	}
}

/**
 * Fetch an invoice by name, resolve its POS Profile print settings,
 * then open the browser print window.
 */
export async function printInvoiceByName(invoiceName, printFormat = null, letterhead = null, paper = "thermal") {
	// Open window synchronously to bypass popup blockers
	const printWindow = window.open("about:blank", "_blank", "width=800,height=600")

	try {
		const invoiceDoc = await call("pos_next.api.invoices.get_invoice", {
			invoice_name: invoiceName,
		})
		if (!invoiceDoc) {
			if (printWindow) printWindow.close()
			throw new Error("Invoice not found")
		}

		const settings = await resolvePrintSettings(invoiceDoc.pos_profile, printFormat, letterhead, paper)
		
		const doctype = invoiceDoc.doctype || "Sales Invoice"
		const format = settings.printFormat

		const params = new URLSearchParams({
			doctype,
			name: invoiceDoc.name,
			format,
			no_letterhead: settings.letterhead ? 0 : 1,
			_lang: "en",
			trigger_print: 1,
			_t: Date.now(),
		})
		if (settings.letterhead) params.append("letterhead", settings.letterhead)

		if (printWindow) {
			printWindow.location.href = `/printview?${params}`
			return true
		} else {
			throw new Error("Popup blocked")
		}
	} catch (error) {
		log.error("printInvoiceByName failed:", error)
		if (printWindow) printWindow.close()

		throw error
	}
}

// ============================================================================
// Silent printing (QZ Tray — no browser dialog)
// ============================================================================

/**
 * Fetch the server-rendered print HTML and send it to a thermal printer
 * via QZ Tray. Uses Frappe's get_html_and_style API which returns the
 * print format HTML + its inline styles (standard.css, print style, custom CSS).
 * Note: print.bundle.css (Bootstrap grid/tables) is NOT included — print
 * formats that rely on Bootstrap layout classes may render differently.
 * Paper size and margins are controlled by the QZ Tray config in qzTray.js.
 */
export async function silentPrintInvoice(invoiceName, printFormat = null, posProfile = null, letterhead = null) {
	let format = printFormat
	if (!format) {
		let resolvedProfile = posProfile
		if (!resolvedProfile) {
			resolvedProfile = (await call("pos_next.api.invoices.get_invoice", { invoice_name: invoiceName }))?.pos_profile
		}
		format = (await resolvePrintSettings(resolvedProfile, null, letterhead)).printFormat
	}

	const result = await call("frappe.www.printview.get_html_and_style", {
		doc: "Sales Invoice",
		name: invoiceName,
		print_format: format,
		no_letterhead: 1,
	})

	const html = result?.html || result?.message?.html
	const style = result?.style || result?.message?.style || ""
	if (!html) throw new Error("Failed to get print HTML from server")

	const fullHTML = `<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><style>${style}</style></head>
<body>${html}</body>
</html>`

	await qzPrintHTML(fullHTML)
	log.info(`Silent print sent for ${invoiceName}`)
	return true
}

/**
 * Try silent print, fall back to browser print on failure.
 * silentPrintInvoice → qzPrintHTML → connect() handles auto-reconnect
 * internally, so no separate connection logic is needed here.
 */
export async function printWithSilentFallback(invoiceData, printFormat = null) {
	const invoiceName = invoiceData?.name
	if (!invoiceName) throw new Error("Invalid invoice data — missing name")
	const posProfile = invoiceData?.pos_profile || invoiceData?.posProfile || null
	const letterhead = invoiceData?.letter_head || null

	try {
		await silentPrintInvoice(invoiceName, printFormat, posProfile, letterhead)
		return { method: "silent", success: true }
	} catch (err) {
		log.warn("Silent print failed, falling back to browser:", err?.message || err)
	}

	try {
		await printInvoiceByName(invoiceName, printFormat)
		return { method: "browser", success: true }
	} catch (err) {
		log.error("Browser print fallback also failed:", err)
		throw err
	}
}

function escapeHtml(text) {
	return String(text || "")
		.replace(/&/g, "&amp;")
		.replace(/</g, "&lt;")
		.replace(/>/g, "&gt;")
		.replace(/"/g, "&quot;")
}

function buildOfflineReceiptHtml(invoiceData) {
	const items = Array.isArray(invoiceData?.items) ? invoiceData.items : []
	const payments = Array.isArray(invoiceData?.payments) ? invoiceData.payments : []
	const title = escapeHtml(invoiceData?.company || invoiceData?.pos_profile || "Mubtkir ERP")
	const refId = escapeHtml(invoiceData?.offline_id || invoiceData?.name || "OFFLINE")
	const customer = escapeHtml(invoiceData?.customer_name || invoiceData?.customer || "")
	const currency = escapeHtml(invoiceData?.currency || "")
	const orderNumber = invoiceData?.mu_order_number ? escapeHtml(String(invoiceData.mu_order_number)) : ""
	const orderTypeRaw = invoiceData?.mu_order_type || ""
	const orderTypeLabel = orderTypeRaw === "Dine-In" ? "🍽️ محلي (Dine-In)" : orderTypeRaw === "Takeaway" ? "🛍️ سفري (Takeaway)" : ""
	const nowStr = new Date().toLocaleString()

	const rowsHtml = items
		.map((it) => {
			const name = escapeHtml(it.item_name || it.item_code)
			const qty = Number(it.qty ?? it.quantity ?? 1)
			const rate = Number(it.rate ?? it.price_list_rate ?? 0)
			const amt = Number(it.amount ?? qty * rate)
			return `<tr>
				<td style="padding:3px 0;text-align:right;">${name}</td>
				<td style="padding:3px 4px;text-align:center;">${qty}</td>
				<td style="padding:3px 0;text-align:left;">${formatCurrency(amt)}</td>
			</tr>`
		})
		.join("")

	const paymentsHtml = payments
		.map(
			(p) =>
				`<div style="display:flex;justify-content:space-between;font-size:12px;"><span>${escapeHtml(
					p.mode_of_payment
				)}</span><span>${formatCurrency(p.amount)} ${currency}</span></div>`
		)
		.join("")

	return `<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head><meta charset="utf-8"><title>${refId}</title>
<style>
body{font-family:Tahoma,Arial,sans-serif;width:72mm;margin:0 auto;padding:4mm;color:#000;font-size:12px;}
.center{text-align:center;}
.sep{border-top:1px dashed #000;margin:6px 0;}
table{width:100%;border-collapse:collapse;font-size:12px;}
th{border-bottom:1px solid #000;padding:3px 0;}
.tot{display:flex;justify-content:space-between;font-weight:bold;font-size:14px;margin-top:4px;}
</style></head>
<body>
<div class="center">
  <div style="font-size:16px;font-weight:bold;">${title}</div>
  ${orderNumber ? `<div style="font-size:20px;font-weight:bold;border:2px solid #000;padding:3px 6px;margin:4px auto;display:inline-block;">طلب #${orderNumber}</div>` : ""}
  ${orderTypeLabel ? `<div style="font-size:13px;font-weight:bold;margin:2px 0;">${orderTypeLabel}</div>` : ""}
  <div style="font-size:11px;">إيصال مؤقت (وضع عدم الاتصال)</div>
  <div style="font-size:11px;">${refId} • ${escapeHtml(nowStr)}</div>
  ${customer ? `<div style="font-size:12px;margin-top:2px;">العميل: ${customer}</div>` : ""}
</div>
<div class="sep"></div>
<table>
  <thead><tr><th style="text-align:right;">الصنف</th><th style="text-align:center;">الكمية</th><th style="text-align:left;">الإجمالي</th></tr></thead>
  <tbody>${rowsHtml}</tbody>
</table>
<div class="sep"></div>
${Number(invoiceData?.total_discount || 0) > 0 ? `<div style="display:flex;justify-content:space-between;"><span>الخصم</span><span>-${formatCurrency(invoiceData.total_discount)} ${currency}</span></div>` : ""}
${Number(invoiceData?.total_tax || 0) > 0 ? `<div style="display:flex;justify-content:space-between;"><span>الضريبة</span><span>${formatCurrency(invoiceData.total_tax)} ${currency}</span></div>` : ""}
<div class="tot"><span>الإجمالي</span><span>${formatCurrency(invoiceData?.grand_total)} ${currency}</span></div>
${paymentsHtml ? `<div class="sep"></div>${paymentsHtml}` : ""}
<div class="sep"></div>
<div class="center" style="font-size:10px;">Powered By Mubtkir ERP</div>
</body></html>`
}

/**
 * Print an offline invoice locally using QZ Tray (if enabled) or Browser Print.
 */
export async function printOfflineReceipt(invoiceData, { useQZ = false } = {}) {
	const html = buildOfflineReceiptHtml(invoiceData)
	if (useQZ) {
		try {
			await qzPrintHTML(html)
			return { method: "silent", success: true }
		} catch (e) {
			log.warn("Offline QZ Tray print failed, falling back to browser print:", e?.message || e)
		}
	}

	const iframe = document.createElement("iframe")
	iframe.style.position = "fixed"
	iframe.style.right = "0"
	iframe.style.bottom = "0"
	iframe.style.width = "0"
	iframe.style.height = "0"
	iframe.style.border = "0"
	document.body.appendChild(iframe)
	const doc = iframe.contentWindow.document
	doc.open()
	doc.write(html)
	doc.close()
	setTimeout(() => {
		try {
			iframe.contentWindow.focus()
			iframe.contentWindow.print()
		} finally {
			setTimeout(() => iframe.remove(), 1500)
		}
	}, 250)
	return { method: "browser", success: true }
}

