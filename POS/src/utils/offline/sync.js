import { call } from "@/utils/apiWrapper"
import { db, getSetting, setSetting } from "./db"
import { syncPendingOfflineCustomers, resolveOfflineCustomerId } from "./customerQueue"
import { offlineState } from "./offlineState"
import { ensureOfflineInvoiceId } from "./offlineInvoiceId"

// Ping server to check connectivity
export const pingServer = async () => {
	if (typeof window === "undefined") return true

	try {
		// Quick ping to check if server is reachable
		const controller = new AbortController()
		const timeoutId = setTimeout(() => controller.abort(), 3000) // 3 second timeout

		const response = await fetch("/api/method/pos_next.api.ping", {
			method: "GET",
			signal: controller.signal,
		})

		clearTimeout(timeoutId)
		const isOnline = response.ok
		// Update centralized state (handles window sync automatically)
		offlineState.setServerOnline(isOnline)
		return isOnline
	} catch (error) {
		// Server unreachable
		offlineState.setServerOnline(false)
		return false
	}
}

// Check if offline - uses centralized state manager
export const isOffline = () => {
	if (typeof window === "undefined") return false
	return offlineState.isOffline
}

// NOTE: Periodic server ping is now handled by the offline worker
// This prevents duplicate pings and centralizes the logic

// Save invoice to offline queue
export const saveOfflineInvoice = async (invoiceData) => {
	try {
		// Validate invoice has items
		if (!invoiceData.items || invoiceData.items.length === 0) {
			throw new Error("Cannot save empty invoice")
		}

		// Clean data (remove reactive properties)
		const cleanData = JSON.parse(JSON.stringify(invoiceData))
		const offlineId = ensureOfflineInvoiceId(cleanData)

		// Add to queue with the same stable idempotency key used by the worker path.
		const id = await db.invoice_queue.add({
			offline_id: offlineId,
			data: cleanData,
			timestamp: Date.now(),
			synced: false,
			retry_count: 0,
		})

		// Update local stock
		await updateLocalStock(cleanData.items)

		console.log("Invoice saved to offline queue", offlineId)
		return { success: true, id, offline_id: offlineId }
	} catch (error) {
		console.error("Error saving offline invoice:", error)
		throw error
	}
}

// Get pending offline invoices
export const getOfflineInvoices = async () => {
	try {
		// Use filter instead of where/equals for boolean values
		const invoices = await db.invoice_queue
			.filter((invoice) => invoice.synced === false)
			.toArray()
		return invoices
	} catch (error) {
		console.error("Error getting offline invoices:", error)
		return []
	}
}

// Get offline invoice count
export const getOfflineInvoiceCount = async () => {
	try {
		// Use filter instead of where/equals for boolean values
		const count = await db.invoice_queue
			.filter((invoice) => invoice.synced === false)
			.count()
		return count
	} catch (error) {
		console.error("Error getting offline invoice count:", error)
		return 0
	}
}

// Sync offline invoices to server
export const syncOfflineInvoices = async () => {
	if (isOffline()) {
		console.log("Cannot sync while offline")
		return { success: 0, failed: 0 }
	}

	const customerSyncResult = await syncPendingOfflineCustomers()
	if (customerSyncResult.failed) {
		console.warn("Some offline customers could not synchronize", customerSyncResult)
	}

	const pendingInvoices = await getOfflineInvoices()
	if (pendingInvoices.length === 0) {
		return { success: 0, failed: 0 }
	}

	let successCount = 0
	let failedCount = 0
	const errors = []

	for (const invoice of pendingInvoices) {
		try {
			// Transform items: map 'quantity' to 'qty' for ERPNext compatibility
			// Offline storage uses 'quantity' (cart format) but server expects 'qty'.
			const invoiceData = { ...invoice.data }

			// Backfill a stable ID for invoices queued by older app versions. Persist
			// it BEFORE the request so a lost response still retries with the same ID.
			const offlineId = invoice.offline_id || ensureOfflineInvoiceId(invoiceData)
			invoiceData.offline_id = offlineId
			if (invoice.offline_id !== offlineId || invoice.data?.offline_id !== offlineId) {
				await db.invoice_queue.update(invoice.id, {
					offline_id: offlineId,
					data: invoiceData,
				})
			}

			if (invoiceData.items && Array.isArray(invoiceData.items)) {
				invoiceData.items = invoiceData.items.map((item) => ({
					...item,
					qty: item.quantity || item.qty || 1,
				}))
			}

			// Resolve offline-created customers before invoice submission.
			if (String(invoiceData.customer || "").startsWith("pos_customer_")) {
				const serverCustomer = await resolveOfflineCustomerId(invoiceData.customer)
				if (!serverCustomer) {
					console.warn("Invoice waiting for offline customer sync", {
						invoiceId: invoice.id,
						customer: invoiceData.customer,
					})
					continue
				}
				invoiceData.customer = serverCustomer
			}

			// Submit invoice to server
			// The API expects 'data' parameter with nested 'invoice' and 'data' keys
			const response = await call("pos_next.api.invoices.submit_invoice", {
				data: JSON.stringify({
					invoice: invoiceData,
					data: {},
				}),
			})

			const serverResult = response?.message || response
			const serverInvoice =
				typeof serverResult === "string"
					? serverResult
					: serverResult?.name || response?.name

			if (serverInvoice) {
				// Mark as synced and retain the server-side invoice mapping for support
				// and diagnostics. Duplicate retries intentionally land here too.
				await db.invoice_queue.update(invoice.id, {
					synced: true,
					server_invoice: serverInvoice,
					synced_at: Date.now(),
					offline_id: invoiceData.offline_id,
					already_synced: Boolean(serverResult?.already_synced),
				})
				successCount++
				console.log(
					`Invoice ${invoice.id} (${invoiceData.offline_id}) synced successfully as ${serverInvoice}`,
				)
			} else {
				throw new Error("Server did not return a Sales Invoice name")
			}
		} catch (error) {
			console.error(`Error syncing invoice ${invoice.id}:`, error)

			// Store error details
			errors.push({
				invoiceId: invoice.id,
				customer: invoice.data.customer || "Walk-in Customer",
				error: error,
			})

			// Increment retry count
			await db.invoice_queue.update(invoice.id, {
				retry_count: (invoice.retry_count || 0) + 1,
			})

			failedCount++

			// If retry count exceeds threshold, mark as failed
			if ((invoice.retry_count || 0) >= 3) {
				await db.invoice_queue.update(invoice.id, {
					sync_failed: true,
					error: error.message,
				})
			}
		}
	}

	// Clean up synced invoices older than 7 days
	const weekAgo = Date.now() - 7 * 24 * 60 * 60 * 1000
	await db.invoice_queue
		.filter((item) => item.synced === true && item.timestamp < weekAgo)
		.delete()

	return { success: successCount, failed: failedCount, errors }
}

// Delete offline invoice
export const deleteOfflineInvoice = async (id) => {
	try {
		await db.invoice_queue.delete(id)
		return true
	} catch (error) {
		console.error("Error deleting offline invoice:", error)
		return false
	}
}

// Update local stock after invoice
export const updateLocalStock = async (items) => {
	try {
		for (const item of items) {
			const stockKey = `${item.item_code}_${item.warehouse}`
			const currentStock = await db.stock.get({
				item_code: item.item_code,
				warehouse: item.warehouse,
			})

			const qty = item.quantity || item.qty || 0
			const newQty = (currentStock?.qty || 0) - qty

			await db.stock.put({
				item_code: item.item_code,
				warehouse: item.warehouse,
				qty: newQty,
				updated_at: Date.now(),
			})
		}
	} catch (error) {
		console.error("Error updating local stock:", error)
	}
}

// Get local stock
export const getLocalStock = async (itemCode, warehouse) => {
	try {
		const stock = await db.stock.get({
			item_code: itemCode,
			warehouse: warehouse,
		})
		return stock?.qty || 0
	} catch (error) {
		console.error("Error getting local stock:", error)
		return 0
	}
}

// Save offline payment
export const saveOfflinePayment = async (paymentData) => {
	try {
		const cleanData = JSON.parse(JSON.stringify(paymentData))

		await db.payment_queue.add({
			data: cleanData,
			timestamp: Date.now(),
			synced: false,
			retry_count: 0,
		})

		console.log("Payment saved to offline queue")
		return true
	} catch (error) {
		console.error("Error saving offline payment:", error)
		throw error
	}
}


// ---------------------------------------------------------------------------
// Shift close queue + sync integrity
// ---------------------------------------------------------------------------

const closingDraftKey = (openingShift) => `closing_shift_draft_${openingShift}`

export const ensureClosingShiftId = (closingShift) => {
	const openingShift = closingShift?.pos_opening_shift || closingShift?.opening_shift
	if (!openingShift) throw new Error("POS Opening Shift is required")
	return closingShift?.close_id || `POS-CLOSE-${openingShift}`
}

export const isNetworkLikeError = (error) => {
	if (offlineState.isOffline) return true
	const text = [
		error?.message,
		error?.exception,
		error?.exc_type,
		error?.resourceError?.message,
	].filter(Boolean).join(" ").toLowerCase()
	return ["network", "failed to fetch", "timeout", "timed out", "abort", "connection", "502", "503", "504"].some((token) => text.includes(token))
}

export const saveClosingShiftDraft = async (openingShift, data) => {
	if (!openingShift || !data) return false
	await setSetting(closingDraftKey(openingShift), {
		data: JSON.parse(JSON.stringify(data)),
		updated_at: Date.now(),
	})
	return true
}

export const getClosingShiftDraft = async (openingShift) => {
	const cached = await getSetting(closingDraftKey(openingShift), null)
	return cached?.data || null
}

export const clearClosingShiftDraft = async (openingShift) => {
	if (!openingShift) return
	await db.settings.delete(closingDraftKey(openingShift))
}

export const savePendingClosingShift = async (closingShift) => {
	const cleanData = JSON.parse(JSON.stringify(closingShift || {}))
	const openingShift = cleanData.pos_opening_shift
	const closeId = ensureClosingShiftId(cleanData)
	cleanData.close_id = closeId

	const existing = await db.closing_shift_queue.where("close_id").equals(closeId).first()
	const row = {
		close_id: closeId,
		opening_shift: openingShift,
		data: cleanData,
		timestamp: existing?.timestamp || Date.now(),
		updated_at: Date.now(),
		synced: false,
		retry_count: existing?.retry_count || 0,
		sync_failed: false,
		error: null,
	}

	if (existing) {
		await db.closing_shift_queue.update(existing.id, row)
		return { ...row, id: existing.id }
	}

	const id = await db.closing_shift_queue.add(row)
	return { ...row, id }
}

export const getPendingClosingShifts = async () => {
	return db.closing_shift_queue.filter((row) => row.synced === false).toArray()
}

export const hasPendingClosingShift = async () => {
	return (await db.closing_shift_queue.filter((row) => row.synced === false).count()) > 0
}

export const syncPendingClosingShifts = async () => {
	if (isOffline()) return { success: 0, failed: 0, deferred: 0 }

	const closings = await getPendingClosingShifts()
	let success = 0
	let failed = 0
	let deferred = 0

	for (const row of closings) {
		try {
			// Never close a shift while one of its offline invoices is still unsynced.
			// This guarantees the server closing summary includes every sale from the shift.
			const pendingInvoices = await getOfflineInvoices()
			const sameShiftPending = pendingInvoices.some((invoice) => {
				const invoiceShift = invoice?.data?.posa_pos_opening_shift
				// Older queued rows may not carry the shift ID. Be conservative and
				// postpone closing until those invoices are resolved too.
				return !invoiceShift || invoiceShift === row.opening_shift
			})
			if (sameShiftPending) {
				deferred++
				continue
			}

			const response = await call("pos_next.api.shifts.submit_closing_shift", {
				closing_shift: JSON.stringify({ ...row.data, close_id: row.close_id }),
			})
			const result = response?.message || response || {}
			const closingName = typeof result === "string" ? result : result?.name
			if (!closingName) throw new Error("Server did not confirm POS Closing Shift")

			await db.closing_shift_queue.update(row.id, {
				synced: true,
				server_closing_shift: closingName,
				synced_at: Date.now(),
				already_closed: Boolean(result?.already_closed),
				error: null,
			})
			await clearClosingShiftDraft(row.opening_shift)

			try {
				const pendingMarker = JSON.parse(localStorage.getItem("pos_shift_pending_close") || "null")
				if (pendingMarker?.opening_shift === row.opening_shift) {
					localStorage.removeItem("pos_shift_pending_close")
				}
			} catch {
				localStorage.removeItem("pos_shift_pending_close")
			}

			success++
			if (typeof window !== "undefined") {
				window.dispatchEvent(new CustomEvent("offlineShiftClosed", { detail: { openingShift: row.opening_shift, closingShift: closingName } }))
			}
		} catch (error) {
			failed++
			await db.closing_shift_queue.update(row.id, {
				retry_count: (row.retry_count || 0) + 1,
				error: error?.message || String(error),
				last_attempt_at: Date.now(),
			})
		}
	}

	const weekAgo = Date.now() - 7 * 24 * 60 * 60 * 1000
	await db.closing_shift_queue
		.filter((item) => item.synced === true && (item.synced_at || item.timestamp) < weekAgo)
		.delete()

	return { success, failed, deferred }
}

let _syncPendingPromise = null

export const syncPendingOperations = async () => {
	if (_syncPendingPromise) return _syncPendingPromise

	_syncPendingPromise = (async () => {
		// Ordering is deliberate: invoices first, then shift close. A closing request
		// is deferred until every queued invoice for that opening shift is confirmed.
		const invoices = await syncOfflineInvoices()
		const closings = await syncPendingClosingShifts()
		return { invoices, closings }
	})()

	try {
		return await _syncPendingPromise
	} finally {
		_syncPendingPromise = null
	}
}

// Auto-sync when coming back online
if (typeof window !== "undefined") {
	// Listen to centralized offline state changes for auto-sync
	offlineState.subscribe(async (state) => {
		// Only sync when transitioning from offline to online
		if (!state.isOffline && state.source !== 'manual') {
			console.log("Back online, syncing pending POS operations...")
			const result = await syncPendingOperations()

			// Dispatch event to notify components to update their pending count
			window.dispatchEvent(
				new CustomEvent("offlineInvoicesSynced", {
					detail: result.invoices,
				}),
			)

			if (result.invoices.success > 0) {
				console.log(`Successfully synced ${result.invoices.success} invoices`)
				if (window.frappe?.msgprint) {
					window.frappe.msgprint({
						title: __("Sync Complete"),
						message: `Successfully synced ${result.invoices.success} offline invoices`,
						indicator: "green",
					})
				}
			}
		}
	})
}

/**
 * Cache unpaid invoice summary
 * @param {Object} summary - Summary object with count, total_outstanding, total_paid
 * @param {string} posProfile - POS Profile name
 * @returns {Promise<boolean>}
 */
export const cacheUnpaidSummary = async (summary, posProfile) => {
	try {
		await db.settings.put({
			key: `unpaid_summary_${posProfile}`,
			value: {
				...summary,
				cached_at: Date.now(),
			},
		})
		log.debug("Cached unpaid invoice summary")
		return true
	} catch (error) {
		log.error("Failed to cache unpaid summary", error)
		return false
	}
}

/**
 * Get cached unpaid invoice summary
 * @param {string} posProfile - POS Profile name
 * @returns {Promise<Object>}
 */
export const getCachedUnpaidSummary = async (posProfile) => {
	try {
		const result = await db.settings.get(`unpaid_summary_${posProfile}`)
		return result?.value || { count: 0, total_outstanding: 0, total_paid: 0 }
	} catch (error) {
		log.error("Failed to get cached unpaid summary", error)
		return { count: 0, total_outstanding: 0, total_paid: 0 }
	}
}

/**
 * Cache unpaid invoices list
 * @param {Array} invoices - List of unpaid invoices
 * @param {string} posProfile - POS Profile name
 * @returns {Promise<boolean>}
 */
export const cacheUnpaidInvoices = async (invoices, posProfile) => {
	try {
		await db.settings.put({
			key: `unpaid_invoices_${posProfile}`,
			value: {
				invoices,
				cached_at: Date.now(),
			},
		})
		log.debug("Cached unpaid invoices list")
		return true
	} catch (error) {
		log.error("Failed to cache unpaid invoices", error)
		return false
	}
}

/**
 * Get cached unpaid invoices list
 * @param {string} posProfile - POS Profile name
 * @returns {Promise<Array>}
 */
export const getCachedUnpaidInvoices = async (posProfile) => {
	try {
		const result = await db.settings.get(`unpaid_invoices_${posProfile}`)
		return result?.value?.invoices || []
	} catch (error) {
		log.error("Failed to get cached unpaid invoices", error)
		return []
	}
}

export const cacheInvoiceHistory = async (invoices, posProfile) => {
	if (!invoices || invoices.length === 0) return false

	try {
		// Clean data and add pos_profile for filtering
		const invoicesToCache = invoices.map((invoice) => ({
			...JSON.parse(JSON.stringify(invoice)),
			pos_profile: posProfile,
			cached_at: Date.now(),
		}))

		await db.invoice_history.bulkPut(invoicesToCache)
		log.info(`Cached ${invoices.length} invoices for offline viewing`)
		return true
	} catch (error) {
		log.error("Failed to cache invoice history", error)
		return false
	}
}

/**
 * Get cached invoice history for offline viewing
 * @param {string} posProfile - POS Profile name (optional filter)
 * @param {Object} options - Query options
 * @param {number} options.limit - Max number of invoices to return
 * @param {string} options.customer - Filter by customer name
 * @param {string} options.fromDate - Filter by posting_date >= fromDate
 * @param {string} options.toDate - Filter by posting_date <= toDate
 * @returns {Promise<Array>}
 */
export const getCachedInvoiceHistory = async (posProfile, options = {}) => {
	try {
		const { limit = 100, customer, fromDate, toDate } = options

		let query = db.invoice_history

		// Filter by POS profile if provided
		if (posProfile) {
			query = query.where("pos_profile").equals(posProfile)
		}

		let invoices = await query.toArray()

		// Apply additional filters
		if (customer) {
			invoices = invoices.filter((inv) =>
				inv.customer?.toLowerCase().includes(customer.toLowerCase()),
			)
		}

		if (fromDate) {
			invoices = invoices.filter((inv) => inv.posting_date >= fromDate)
		}

		if (toDate) {
			invoices = invoices.filter((inv) => inv.posting_date <= toDate)
		}

		// Sort by posting_date descending (newest first)
		invoices.sort((a, b) => {
			const dateA = new Date(b.posting_date + " " + (b.posting_time || "00:00:00"))
			const dateB = new Date(a.posting_date + " " + (a.posting_time || "00:00:00"))
			return dateA - dateB
		})

		return invoices.slice(0, limit)
	} catch (error) {
		log.error("Failed to get cached invoice history", error)
		return []
	}
}

/**
 * Clear cached invoice history
 * @param {string} posProfile - Optional POS Profile to clear (clears all if not provided)
 * @returns {Promise<boolean>}
 */
export const clearInvoiceHistoryCache = async (posProfile) => {
	try {
		if (posProfile) {
			await db.invoice_history.where("pos_profile").equals(posProfile).delete()
		} else {
			await db.invoice_history.clear()
		}
		log.info("Invoice history cache cleared")
		return true
	} catch (error) {
		log.error("Failed to clear invoice history cache", error)
		return false
	}
}
