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
				if (paper === "a4" && !Number(doc.mu_allow_a4_print)) {
					throw new Error("A4 printing is disabled for this POS Profile")
				}
				const selected = paper === "a4" ? doc.mu_a4_print_format : (doc.mu_thermal_print_format || doc.print_format)
				if (!selected) throw missingFormat()
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
export async function silentPrintInvoice(invoiceName, printFormat = null) {
	const format = (await resolvePrintSettings((await call("pos_next.api.invoices.get_invoice", { invoice_name: invoiceName }))?.pos_profile, printFormat, null)).printFormat

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

	try {
		await silentPrintInvoice(invoiceName, printFormat)
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

