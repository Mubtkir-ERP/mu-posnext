import { call } from "@/utils/apiWrapper"
import { db, getSetting, setSetting } from "./db"
import { offlineState } from "./offlineState"

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

		// Add to queue
		await db.invoice_queue.add({
			data: cleanData,
			timestamp: Date.now(),
			synced: false,
			retry_count: 0,
		})

		// Update local stock
		await updateLocalStock(cleanData.items)

		console.log("Invoice saved to offline queue")
		return true
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
			// Offline storage uses 'quantity' (cart format) but server expects 'qty'
			const invoiceData = { ...invoice.data }
			if (invoiceData.items && Array.isArray(invoiceData.items)) {
				invoiceData.items = invoiceData.items.map((item) => ({
					...item,
					qty: item.quantity || item.qty || 1,
				}))
			}

			// Submit invoice to server
			// The API expects 'data' parameter with nested 'invoice' and 'data' keys
			const response = await call("pos_next.api.invoices.submit_invoice", {
				data: JSON.stringify({
					invoice: invoiceData,
					data: {},
				}),
			})

			if (response.message || response.name) {
				// Mark as synced
				await db.invoice_queue.update(invoice.id, { synced: true })
				successCount++
				console.log(
					`Invoice ${invoice.id} synced successfully as ${response.name || response.message}`,
				)
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

// Auto-sync when coming back online
if (typeof window !== "undefined") {
	// Listen to centralized offline state changes for auto-sync
	offlineState.subscribe(async (state) => {
		// Only sync when transitioning from offline to online
		if (!state.isOffline && state.source !== 'manual') {
			console.log("Back online, syncing pending invoices...")
			const result = await syncOfflineInvoices()

			// Dispatch event to notify components to update their pending count
			window.dispatchEvent(
				new CustomEvent("offlineInvoicesSynced", {
					detail: result,
				}),
			)

			if (result.success > 0) {
				console.log(`Successfully synced ${result.success} invoices`)
				if (window.frappe?.msgprint) {
					window.frappe.msgprint({
						title: __("Sync Complete"),
						message: `Successfully synced ${result.success} offline invoices`,
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
