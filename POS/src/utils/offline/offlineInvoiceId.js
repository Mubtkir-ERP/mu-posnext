/**
 * Generate and preserve a stable identifier for an invoice created offline.
 *
 * The identifier is sent to the server on every retry. The server stores the
 * mapping in Offline Invoice Sync so the same offline sale can never create a
 * second Sales Invoice just because the HTTP response was lost.
 */
export function generateOfflineInvoiceId() {
	if (globalThis.crypto?.randomUUID) {
		return `POS-OFFLINE-${globalThis.crypto.randomUUID()}`
	}

	// Fallback for older WebViews/browsers without crypto.randomUUID().
	const randomPart = Math.random().toString(36).slice(2, 12)
	return `POS-OFFLINE-${Date.now().toString(36)}-${randomPart}`
}

/**
 * Ensure invoice data has one stable offline_id and return it.
 * Mutates the supplied plain object intentionally so the ID is persisted with
 * the exact payload that will later be retried.
 */
export function ensureOfflineInvoiceId(invoiceData) {
	if (!invoiceData || typeof invoiceData !== "object") {
		throw new Error("Invoice data is required to generate an offline ID")
	}

	if (!invoiceData.offline_id) {
		invoiceData.offline_id = generateOfflineInvoiceId()
	}

	return invoiceData.offline_id
}
