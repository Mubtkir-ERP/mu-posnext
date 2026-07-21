import { call } from "@/utils/apiWrapper"
import { printHTML } from "@/utils/qzTray"

/**
 * Print kitchen tickets for an order, one per station/printer.
 *
 * The backend groups the ordered lines by each item's kitchen station
 * (Item Group → custom_kitchen_station) and returns a rendered ticket per
 * station that has a printer mapped in POS Settings. If no kitchen printers
 * are configured, the backend returns [] and this is a silent no-op.
 *
 * @param {string} posProfile
 * @param {Array<{item_code,item_name,qty,modifier_summary,item_note}>} items
 * @param {string} [invoiceName]
 * @param {string} [orderNote]
 * @returns {Promise<{printed:number,total:number}>}
 */
export async function printKitchenTickets(posProfile, items, invoiceName = null, orderNote = null) {
	try {
		if (!items || !items.length) return { printed: 0, total: 0 }
		const tickets = await call("pos_next.api.kitchen.get_kitchen_tickets", {
			pos_profile: posProfile,
			items: JSON.stringify(items),
			invoice_name: invoiceName,
			order_note: orderNote,
		})
		if (!Array.isArray(tickets) || !tickets.length) return { printed: 0, total: 0 }

		let printed = 0
		for (const t of tickets) {
			try {
				await printHTML(t.html, t.printer_name)
				printed++
			} catch (e) {
				console.error("Kitchen print failed for printer", t.printer_name, e)
			}
		}
		return { printed, total: tickets.length }
	} catch (e) {
		console.error("Kitchen tickets error", e)
		return { printed: 0, total: 0, error: e }
	}
}
