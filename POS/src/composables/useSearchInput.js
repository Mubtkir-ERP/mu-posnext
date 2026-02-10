import { ref, watch, nextTick, onUnmounted } from "vue"

/**
 * Composable for search input, barcode scanning, and auto-add logic.
 *
 * Owns all search-input state, timers, and event handlers with proper
 * concurrency control.  Extracted from ItemsSelector.vue to fix:
 *   - Race condition: autoSearchTimer firing after clearSearch
 *   - No concurrency guard on overlapping handleBarcodeSearch calls
 *   - Dead scanner-speed-detection code
 *   - Scattered focus / getElementById fallbacks
 *   - handleSearchClick skipping timer cleanup
 *
 * @param {Object} options
 * @param {Object} options.itemStore          - Pinia item-search store
 * @param {import('vue').Ref} options.filteredItems - ref from storeToRefs
 * @param {(item: Object, autoAdd: boolean) => boolean} options.onItemFound
 *        Component's selectItem(). Returns true if item was accepted.
 * @param {Object} options.showWarning        - useToast().showWarning
 * @param {import('vue').Ref<boolean>} options.isAnyDialogOpen
 */
export function useSearchInput({ itemStore, filteredItems, onItemFound, showWarning, isAnyDialogOpen }) {
	// --- Reactive state (exposed) ---
	const searchInputRef = ref(null)
	const scannerEnabled = ref(false)
	const autoAddEnabled = ref(false)

	// --- Internal (non-reactive) ---
	let autoSearchTimer = null
	let barcodeSearchGeneration = 0

	// ---- Timer helpers ----

	function clearAutoSearchTimer() {
		if (autoSearchTimer) {
			clearTimeout(autoSearchTimer)
			autoSearchTimer = null
		}
	}

	// ---- Focus ----

	function focusSearchInput() {
		nextTick(() => {
			if (searchInputRef.value) {
				searchInputRef.value.focus()
			}
		})
	}

	// ---- Clear ----

	/** Atomic clear: timer -> store -> DOM input.value -> refocus */
	function clearSearchAndResetInput() {
		clearAutoSearchTimer()
		itemStore.clearSearch()
		if (searchInputRef.value) {
			searchInputRef.value.value = ""
		}
		if (scannerEnabled.value || autoAddEnabled.value) {
			focusSearchInput()
		}
	}

	// ---- Event handlers ----

	function handleKeyDown(event) {
		if (event.key === "Enter") {
			event.preventDefault()

			// Clear timer BEFORE the async call (fixes race condition)
			clearAutoSearchTimer()

			handleBarcodeSearch(autoAddEnabled.value)
			return
		}
		// All other keys: no special handling needed.
		// Dead scanner-speed-detection code removed.
	}

	/**
	 * Handles the `input` event on the search <input>.
	 *
	 * Two independent timers exist by design:
	 *   1. itemStore.setSearchTerm() triggers the store's own debounce for
	 *      updating the displayed item grid.
	 *   2. autoSearchTimer (500 ms) triggers auto-add behaviour — completely
	 *      separate from display.
	 */
	function handleSearchInput(event) {
		const value = event.target.value

		// Guard: ignore stale empty events after search was already cleared
		if (!value && !itemStore.searchTerm) {
			return
		}

		itemStore.setSearchTerm(value)

		clearAutoSearchTimer()

		// Auto-add: after user stops typing for 500 ms, trigger barcode search
		if (autoAddEnabled.value && value.trim().length > 0) {
			autoSearchTimer = setTimeout(() => {
				handleBarcodeSearch(true)
			}, 500)
		}
	}

	/** Clicking the search input clears search + timer atomically. */
	function handleSearchClick() {
		clearSearchAndResetInput()
	}

	/**
	 * Barcode / exact-match search with generation-counter concurrency guard.
	 *
	 * If a newer call starts while we're awaiting the API, the older call
	 * bails out — preventing double-add and stale-result bugs.
	 */
	async function handleBarcodeSearch(forceAutoAdd = false) {
		const barcode = itemStore.searchTerm?.trim()
		if (!barcode) return

		const shouldAutoAdd = forceAutoAdd || (scannerEnabled.value && autoAddEnabled.value)

		// Increment generation; capture our own value
		const myGeneration = ++barcodeSearchGeneration

		try {
			const item = await itemStore.searchByBarcode(barcode)

			// Bail if a newer search started while we were awaiting
			if (myGeneration !== barcodeSearchGeneration) return

			if (item) {
				if (onItemFound(item, shouldAutoAdd)) {
					clearSearchAndResetInput()
				}
				return
			}
		} catch (error) {
			console.error("Barcode API error:", error)
			if (myGeneration !== barcodeSearchGeneration) return
		}

		// Bail again after the catch — another search may have started
		if (myGeneration !== barcodeSearchGeneration) return

		// Fallback: single match in filtered results → auto-select
		if (filteredItems.value.length === 1) {
			if (onItemFound(filteredItems.value[0], shouldAutoAdd)) {
				clearSearchAndResetInput()
			}
		} else if (filteredItems.value.length === 0) {
			showWarning(__('Item Not Found: No item found with barcode: {0}', [barcode]))
			if (shouldAutoAdd) {
				clearSearchAndResetInput()
			}
		} else {
			if (shouldAutoAdd) {
				showWarning(__('Multiple Items Found: {0} items match barcode. Please refine search.', [filteredItems.value.length]))
			} else {
				showWarning(__('Multiple Items Found: {0} items match. Please select one.', [filteredItems.value.length]))
			}
		}
	}

	// ---- Toggles ----

	function toggleBarcodeScanner() {
		scannerEnabled.value = !scannerEnabled.value

		if (scannerEnabled.value) {
			autoAddEnabled.value = true
			focusSearchInput()
		} else {
			autoAddEnabled.value = false
		}
	}

	function toggleAutoAdd() {
		autoAddEnabled.value = !autoAddEnabled.value

		if (autoAddEnabled.value && !scannerEnabled.value) {
			scannerEnabled.value = true
		}

		if (!autoAddEnabled.value) {
			clearAutoSearchTimer()
		}

		if (autoAddEnabled.value) {
			focusSearchInput()
		}
	}

	// ---- Dialog-close watcher ----
	// Refocuses the search bar when all dialogs close (scanner/auto-add modes)
	const stopDialogWatcher = watch(isAnyDialogOpen, (isOpen, wasOpen) => {
		if (wasOpen && !isOpen && (scannerEnabled.value || autoAddEnabled.value)) {
			focusSearchInput()
		}
	})

	// ---- Cleanup ----
	function cleanup() {
		clearAutoSearchTimer()
		stopDialogWatcher()
	}

	onUnmounted(cleanup)

	return {
		// State
		searchInputRef,
		scannerEnabled,
		autoAddEnabled,

		// Event handlers
		handleSearchInput,
		handleKeyDown,
		handleSearchClick,

		// Toggles
		toggleBarcodeScanner,
		toggleAutoAdd,

		// Utilities
		focusSearchInput,
		clearSearchAndResetInput,
		cleanup,
	}
}
