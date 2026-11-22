import { call } from "@/utils/apiWrapper"
import { printHTML } from "@/utils/qzTray"

function printViaBrowser(html) {
	const iframe = document.createElement("iframe")
	iframe.style.position = "fixed"
	iframe.style.left = "-9999px"
	iframe.style.top = "0"
	iframe.style.width = "800px"
	iframe.style.height = "600px"
	iframe.style.border = "0"
	iframe.style.opacity = "0"
	iframe.style.pointerEvents = "none"
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
}

/**
 * Print kitchen tickets for an order, one per station/printer.
 * Supports QZ Tray, Network IP (ESC/POS), and Browser Print.
 */
export async function printKitchenTickets(
	posProfile,
	items,
	invoiceName = null,
	orderNote = null,
	customerName = null,
	orderNumber = null,
	orderType = null
) {
	try {
		if (!items || !items.length) return { printed: 0, total: 0 }
		const tickets = await call("pos_next.api.kitchen.get_kitchen_tickets", {
			pos_profile: posProfile,
			items: JSON.stringify(items),
			invoice_name: invoiceName,
			order_note: orderNote,
			customer_name: customerName,
			order_number: orderNumber,
			order_type: orderType,
		})
		if (!Array.isArray(tickets) || !tickets.length) return { printed: 0, total: 0 }

		let printed = 0
		for (const t of tickets) {
			try {
				const method = t.print_method || "QZ Tray"
				if (method === "Network IP (ESC/POS)") {
					await call("pos_next.api.kitchen.print_network_ticket", {
						printer_ip: t.printer_ip,
						printer_port: t.printer_port || 9100,
						station_title: t.station_title,
						invoice_name: invoiceName,
						lines: JSON.stringify(t.lines || []),
						customer_name: customerName,
						order_note: orderNote,
						order_number: orderNumber,
						order_type: orderType,
					})
				} else if (method === "Browser Print") {
					printViaBrowser(t.html)
				} else {
					await printHTML(t.html, t.printer_name)
				}
				printed++
			} catch (e) {
				console.error("Kitchen print failed for station", t.station, e)
			}
		}
		return { printed, total: tickets.length }
	} catch (e) {
		console.error("Kitchen tickets error", e)
		return { printed: 0, total: 0, error: e }
	}
}
