import { defineStore } from "pinia";
import { computed, ref, watch } from "vue";
import { usePOSCartStore } from "./posCart";
import { usePOSSettingsStore } from "./posSettings";
import { usePOSShiftStore } from "./posShift";
import { resolveTerminalIdentity } from "@/utils/terminalIdentity";
import { call } from "@/utils/apiWrapper";

const CHANNEL_PREFIX = "posnext-customer-display-v1";
const STORAGE_PREFIX = "posnext_customer_display_state_v1";
const PRINT_PROVIDER_CHANGED_EVENT = "posnext:print-provider-changed";

function enabled(value, fallback = false) {
	if (value === null || value === undefined || value === "") return fallback;
	if (typeof value === "boolean") return value;
	if (typeof value === "number") return value === 1;
	return ["1", "true", "yes", "on"].includes(String(value).trim().toLowerCase());
}

function number(value) {
	const parsed = Number(value || 0);
	return Number.isFinite(parsed) ? parsed : 0;
}

function customerDisplayName(customer, mode = "First Name") {
	if (!customer) return "";
	const full = String(
		customer.customer_name || customer.full_name || customer.name || customer
	).trim();
	if (!full) return "";
	if (mode === "Full Name") return full;
	if (mode === "Masked") {
		return full
			.split(/\s+/)
			.map((part) => (part.length <= 1 ? "*" : `${part[0]}${"*".repeat(Math.min(part.length - 1, 6))}`))
			.join(" ");
	}
	return full.split(/\s+/)[0];
}

function getBarcode(item) {
	return item?.barcode || item?.item_barcode || item?.barcode_value || item?.scan_code || "";
}

function getImage(item) {
	return item?.image || item?.item_image || item?.website_image || item?.thumbnail || item?.image_url || "";
}

function getOriginalPrice(item) {
	return number(item?.price_list_rate ?? item?.original_rate ?? item?.rate);
}

function getFinalPrice(item) {
	return number(item?.rate ?? item?.price_list_rate);
}

function serializeItem(item) {
	const qty = number(item?.quantity ?? item?.qty);
	const original = getOriginalPrice(item);
	const finalPrice = getFinalPrice(item);
	const discountAmount = number(
		item?.discount_amount ?? Math.max(0, original - finalPrice)
	);
	const discountPercentage = number(
		item?.discount_percentage ?? (original > 0 ? (discountAmount / original) * 100 : 0)
	);
	return {
		item_code: item?.item_code || "",
		item_name: item?.item_name || item?.item_code || "",
		barcode: getBarcode(item),
		image: getImage(item),
		quantity: qty,
		uom: item?.uom || item?.stock_uom || "",
		original_price: original,
		discount_amount: discountAmount,
		discount_percentage: discountPercentage,
		final_price: finalPrice,
		line_total: number(item?.amount ?? finalPrice * qty),
	};
}

export const useCustomerDisplayStore = defineStore("customerDisplay", () => {
	const cartStore = usePOSCartStore();
	const settingsStore = usePOSSettingsStore();
	const shiftStore = usePOSShiftStore();
	const state = ref(null);
	const posProfile = ref("");
	const paymentSnapshot = ref(null);
	const paymentActive = ref(false);
	const paymentCustomerCredit = ref(null);
	const customerCreditBalance = ref(null);
	const customerWalletBalance = ref(null);
	const customerWalletProgram = ref("");
	const customerWalletEnabled = ref(false);
	const completedWalletAdded = ref(0);
	const customerFinancialKey = ref("");
	const transactionMode = ref("SALE");
	const initialized = ref(false);
	const terminalId = ref("");
	const terminalSource = ref("");
	let channel = null;
	let stopCartWatch = null;
	let stopCustomerFinancialWatch = null;
	let thankYouTimer = null;
	let syncTimer = null;
	let terminalChangeHandler = null;
	let completedHoldUntil = 0;
	let previouslySeenQuantities = new Map();
	let latestScannedKey = "";
	let latestQuantityDelta = 0;

	function cartRowIdentity(item) {
		return JSON.stringify([
			String(item?.item_code || item?.item_name || ""),
			String(item?.uom || item?.stock_uom || ""),
			String(item?.batch_no || ""),
			String(item?.serial_no || ""),
		]);
	}

	function latestCartRowIndex(rows) {
		const nextQuantities = new Map();
		let newestIncrease = "";
		let newestDecrease = "";
		let nextDelta = 0;
		for (const row of rows) {
			const key = cartRowIdentity(row);
			nextQuantities.set(key, (nextQuantities.get(key) || 0) + number(row?.quantity ?? row?.qty));
		}
		for (const [key, qty] of nextQuantities) {
			const difference = qty - (previouslySeenQuantities.get(key) || 0);
			if (difference > 0.000001) {
				newestIncrease = key;
				nextDelta = difference;
			} else if (difference < -0.000001 && !newestIncrease) {
				newestDecrease = key;
				nextDelta = difference;
			}
		}
		previouslySeenQuantities = nextQuantities;
		if (newestIncrease || newestDecrease) {
			latestScannedKey = newestIncrease || newestDecrease;
			latestQuantityDelta = nextDelta;
		}
		if (!rows.length) {
			latestScannedKey = "";
			latestQuantityDelta = 0;
			return -1;
		}
		let index = rows.findIndex((row) => cartRowIdentity(row) === latestScannedKey);
		if (index < 0) {
			index = rows.length - 1;
			latestScannedKey = cartRowIdentity(rows[index]);
			latestQuantityDelta = 0;
		}
		return index;
	}

	const isEnabled = computed(() => enabled(settingsStore.settings?.customer_display_enabled));

	function storageKey(profile = posProfile.value, terminal = terminalId.value) {
		return `${STORAGE_PREFIX}:${profile || "default"}:${terminal || "unassigned"}`;
	}

	function channelName(profile = posProfile.value, terminal = terminalId.value) {
		return `${CHANNEL_PREFIX}:${profile || "default"}:${terminal || "unassigned"}`;
	}

	function visibility() {
		const s = settingsStore.settings || {};
		return {
			company_name: enabled(s.cd_show_company_name, true),
			welcome_text: enabled(s.cd_show_welcome_text, true),
			pos_location: enabled(s.cd_show_pos_location, true),
			pos_number: enabled(s.cd_show_pos_number, true),
			product_image: enabled(s.cd_show_product_image, true),
			item_name: enabled(s.cd_show_item_name, true),
			barcode: enabled(s.cd_show_barcode, true),
			quantity: enabled(s.cd_show_quantity, true),
			original_price: enabled(s.cd_show_original_price, true),
			discount_amount: enabled(s.cd_show_discount_amount, true),
			discount_percentage: enabled(s.cd_show_discount_percentage, false),
			final_price: enabled(s.cd_show_final_price, true),
			running_qty: enabled(s.cd_show_running_qty, true),
			subtotal: enabled(s.cd_show_subtotal, true),
			total_discount: enabled(s.cd_show_total_discount, true),
			grand_total: enabled(s.cd_show_grand_total, true),
			customer_name: enabled(s.cd_show_customer_name, true),
			loyalty_points: enabled(s.cd_show_loyalty_points, true),
			loyalty_earned: enabled(s.cd_show_loyalty_earned, true),
			customer_credit: enabled(s.cd_show_customer_credit, true),
			payment_method: enabled(s.cd_show_payment_method, true),
			amount_paid: enabled(s.cd_show_amount_paid, true),
			remaining_balance: enabled(s.cd_show_remaining_balance, true),
			change: enabled(s.cd_show_change, true),
			invoice_number: enabled(s.cd_show_invoice_number, true),
		};
	}

	function basePayload(mode = "IDLE") {
		const s = settingsStore.settings || {};
		return {
			version: 1,
			updated_at: new Date().toISOString(),
			mode,
			transaction_mode: transactionMode.value,
			pos_profile: posProfile.value || cartStore.posProfile || "",
			terminal_id: terminalId.value || "",
			terminal_source: terminalSource.value || "browser",
			company: {
				name: s.customer_display_company_name || "",
				logo: shiftStore.currentCompany?.company_logo || shiftStore.currentProfile?.company_logo || "",
				welcome_text: s.customer_display_welcome_text || "Welcome",
				location: s.customer_display_pos_location || "",
				pos_number: visibility().pos_number ? (terminalId.value || "") : null,
			},
			theme: s.customer_display_theme || "Dark",
			currency_label: s.customer_display_currency_label || "KD",
			idle: {
				mode: s.customer_display_idle_mode || "Welcome",
				image: s.customer_display_idle_image || "",
				video: s.customer_display_idle_video || "",
			},
			thank_you: {
				enabled: enabled(s.cd_enable_thank_you, true),
				title: s.customer_display_thank_you_title || "Thank You",
				message: s.customer_display_thank_you_message || "Thank you for shopping with us",
				duration: Math.max(1, number(s.customer_display_thank_you_duration) || 5),
			},
			visibility: visibility(),
			customer: null,
			current_item: null,
			items: [],
			totals: { quantity: 0, subtotal: 0, discount: 0, grand_total: 0 },
			payment: null,
			transaction: null,
		};
	}

	function buildCustomer() {
		const customer = cartStore.customer;
		if (!customer) return null;
		const v = visibility();
		return {
			name: v.customer_name
				? customerDisplayName(customer, settingsStore.settings?.cd_customer_name_mode)
				: null,
			loyalty_program: v.loyalty_points && customerWalletEnabled.value
				? (customerWalletProgram.value || customer.loyalty_program || null)
				: null,
			wallet_balance: v.loyalty_points && customerWalletEnabled.value
				? number(customerWalletBalance.value)
				: null,
			wallet_used: v.loyalty_points
				? number(paymentSnapshot.value?.wallet_used)
				: null,
			wallet_added: v.loyalty_earned
				? number(completedWalletAdded.value)
				: null,
			credit: v.customer_credit
				? number(
					paymentCustomerCredit.value !== null
						? paymentCustomerCredit.value
						: customerCreditBalance.value !== null
							? customerCreditBalance.value
							: (customer.customer_credit ?? customer.credit_balance ?? customer.available_credit)
				)
				: null,
		};
	}

	function customerKey(customer = cartStore.customer) {
		return String(customer?.name || customer?.customer || customer?.customer_name || customer || "").trim();
	}

	async function refreshCustomerFinancials(customer = cartStore.customer) {
		const key = customerKey(customer);
		if (!key) {
			customerFinancialKey.value = "";
			customerCreditBalance.value = null;
			customerWalletBalance.value = null;
			customerWalletProgram.value = "";
			customerWalletEnabled.value = false;
			completedWalletAdded.value = 0;
			paymentCustomerCredit.value = null;
			syncCartNow();
			return;
		}
		const company = shiftStore.profileCompany || shiftStore.currentProfile?.company || "";
		if (!company) return;

		const requestKey = `${company}::${key}`;
		customerFinancialKey.value = requestKey;
		completedWalletAdded.value = 0;

		const requests = [];
		if (visibility().customer_credit) {
			requests.push(
				call("pos_next.api.credit_sales.get_customer_balance", { customer: key, company })
					.then((result) => ({ type: "credit", result }))
			);
		}
		if (visibility().loyalty_points || visibility().loyalty_earned) {
			requests.push(
				call("pos_next.api.wallet.get_wallet_info", {
					customer: key,
					company,
					pos_profile: posProfile.value || cartStore.posProfile || "",
				}).then((result) => ({ type: "wallet", result }))
			);
		}

		const results = await Promise.allSettled(requests);
		if (customerFinancialKey.value !== requestKey) return;

		for (const entry of results) {
			if (entry.status !== "fulfilled") continue;
			const { type, result } = entry.value;
			const data = result?.message || result || {};
			if (type === "credit") {
				customerCreditBalance.value = number(data.available_credit ?? data.total_credit ?? 0);
				if (!paymentActive.value) paymentCustomerCredit.value = null;
			} else if (type === "wallet") {
				customerWalletEnabled.value = Boolean(number(data.wallet_enabled));
				customerWalletBalance.value = number(data.wallet_balance);
				customerWalletProgram.value = String(customer?.loyalty_program || data.loyalty_program || "");
			}
		}

		syncCartNow();
	}

	function walletUsedFromPayments(rows = []) {
		return (rows || []).reduce((total, row) => {
			const mode = String(row?.mode_of_payment || row?.type || "").trim().toLowerCase();
			const isWallet = Boolean(row?.is_wallet_payment) || mode === "loyalty wallet" || mode.includes("loyalty wallet");
			return isWallet ? total + Math.abs(number(row?.amount)) : total;
		}, 0);
	}

	async function refreshCompletedWallet(invoiceName, customer, company) {
		if (!invoiceName || !customer || !company) return;
		try {
			const result = await call("pos_next.api.wallet.get_wallet_display_summary", {
				customer,
				company,
				pos_profile: posProfile.value || cartStore.posProfile || "",
				invoice: invoiceName,
			});
			const data = result?.message || result || {};
			if (state.value?.transaction?.invoice_number !== invoiceName) return;

			customerWalletEnabled.value = Boolean(number(data.wallet_enabled));
			customerWalletBalance.value = number(data.wallet_balance);
			customerWalletProgram.value = String(data.loyalty_program || customerWalletProgram.value || "");
			completedWalletAdded.value = number(data.wallet_added);
			if (paymentSnapshot.value) {
				paymentSnapshot.value = {
					...paymentSnapshot.value,
					wallet_used: number(data.wallet_used),
					wallet_added: number(data.wallet_added),
					wallet_balance: number(data.wallet_balance),
					loyalty_program: data.loyalty_program || customerWalletProgram.value || null,
				};
			}

			const refreshed = { ...state.value };
			refreshed.customer = {
				...(refreshed.customer || {}),
				loyalty_program: data.loyalty_program || customerWalletProgram.value || null,
				wallet_balance: number(data.wallet_balance),
				wallet_used: number(data.wallet_used),
				wallet_added: number(data.wallet_added),
			};
			refreshed.payment = paymentSnapshot.value;
			publish(refreshed);
		} catch (_) {}
	}

	function buildCartPayload(mode = null) {
		const v = visibility();
		const latestIndex = latestCartRowIndex(cartStore.invoiceItems || []);
		const items = (cartStore.invoiceItems || []).map(serializeItem).map((item) => ({
			...item,
			item_name: v.item_name ? item.item_name : null,
			barcode: v.barcode ? item.barcode : null,
			image: v.product_image ? item.image : null,
			quantity: v.quantity || v.running_qty ? item.quantity : null,
			original_price: v.original_price ? item.original_price : null,
			discount_amount: v.discount_amount ? item.discount_amount : null,
			discount_percentage: v.discount_percentage ? item.discount_percentage : null,
			final_price: v.final_price ? item.final_price : null,
		}));
		const totalQty = (cartStore.invoiceItems || []).reduce((sum, item) => sum + number(item.quantity ?? item.qty), 0);
		const defaultMode = transactionMode.value !== "SALE"
			? transactionMode.value
			: (items.length ? "CART" : "IDLE");
		const payload = basePayload(mode || defaultMode);
		payload.customer = buildCustomer();
		if (payload.customer && visibility().customer_credit && paymentCustomerCredit.value !== null) {
			payload.customer.credit = paymentCustomerCredit.value;
		}
		payload.items = items;
		payload.latest_item_index = latestIndex;
		payload.current_item = latestIndex >= 0 ? items[latestIndex] : null;
		payload.latest_quantity_delta = v.quantity && latestIndex >= 0 ? latestQuantityDelta : null;
		payload.totals = {
			quantity: v.running_qty ? totalQty : null,
			subtotal: v.subtotal ? number(cartStore.subtotal) : null,
			discount: v.total_discount ? number(cartStore.totalDiscount) : null,
			grand_total: v.grand_total ? number(cartStore.grandTotal) : null,
		};
		payload.payment = paymentSnapshot.value;
		return payload;
	}

	function publish(payload) {
		if (!isEnabled.value && payload?.mode !== "DISABLED") return;
		state.value = payload;
		try {
			localStorage.setItem(storageKey(), JSON.stringify(payload));
		} catch (_) {}
		try {
			channel?.postMessage(payload);
		} catch (_) {}
		try {
			window.dispatchEvent(new CustomEvent("posnext:customer-display", { detail: payload }));
		} catch (_) {}
	}

	function syncCartNow() {
		if (!initialized.value || !isEnabled.value) return;

		const hasItems = (cartStore.invoiceItems || []).length > 0;
		const currentMode = state.value?.mode || "IDLE";

		if (paymentActive.value) {
			publish(buildCartPayload("PAYMENT"));
			return;
		}

		if (hasItems && ["THANK_YOU", "IDLE", "RETURN", "EXCHANGE"].includes(currentMode)) {
			clearTimeout(thankYouTimer);
			thankYouTimer = null;
			completedHoldUntil = 0;
			paymentSnapshot.value = null;
			paymentActive.value = false;
			paymentCustomerCredit.value = null;
			completedWalletAdded.value = 0;
			transactionMode.value = "SALE";
		}

		if (!hasItems && completedHoldUntil > Date.now() && ["THANK_YOU", "RETURN", "EXCHANGE"].includes(currentMode)) {
			return;
		}

		publish(buildCartPayload());
	}

	function scheduleCartSync() {
		clearTimeout(syncTimer);
		syncTimer = setTimeout(syncCartNow, 75);
	}

	function setPayment(paymentData) {
		if (!isEnabled.value) return;

		if (paymentData?.is_open === false) {
			paymentActive.value = false;
			paymentCustomerCredit.value = null;
			const currentMode = state.value?.mode || "IDLE";
			if (!["THANK_YOU", "RETURN", "EXCHANGE"].includes(currentMode)) {
				paymentSnapshot.value = null;
				publish(buildCartPayload());
			}
			return;
		}

		paymentActive.value = true;
		const paid = number(paymentData?.paid_amount);
		const change = number(paymentData?.change_amount);
		const outstanding = number(
			paymentData?.outstanding_amount ?? Math.max(0, number(cartStore.grandTotal) - paid)
		);
		const v = visibility();
		if (paymentData?.customer_credit_balance !== null && paymentData?.customer_credit_balance !== undefined) {
			paymentCustomerCredit.value = number(paymentData.customer_credit_balance);
		}

		const walletUsed = walletUsedFromPayments(paymentData?.payments || []);
		paymentSnapshot.value = {
			methods: v.payment_method
				? (paymentData?.payments || []).map((row) => ({
					mode_of_payment: row.mode_of_payment || row.type || "",
					amount: number(row.amount),
					is_wallet_payment: Boolean(row.is_wallet_payment),
				}))
				: [],
			paid_amount: v.amount_paid ? paid : null,
			remaining_balance: v.remaining_balance ? outstanding : null,
			change_amount: v.change ? change : null,
			customer_credit_balance: v.customer_credit ? paymentCustomerCredit.value : null,
			wallet_used: v.loyalty_points ? walletUsed : null,
			wallet_added: v.loyalty_earned ? number(completedWalletAdded.value) : null,
			wallet_balance: v.loyalty_points && customerWalletEnabled.value ? number(customerWalletBalance.value) : null,
			loyalty_program: v.loyalty_points && customerWalletEnabled.value ? (customerWalletProgram.value || null) : null,
		};
		const payload = buildCartPayload("PAYMENT");
		if (payload.customer && v.customer_credit && paymentCustomerCredit.value !== null) {
			payload.customer.credit = paymentCustomerCredit.value;
		}
		publish(payload);
	}

	function setTransactionMode(mode = "SALE") {
		transactionMode.value = String(mode || "SALE").toUpperCase();
		if (isEnabled.value) publish(buildCartPayload(transactionMode.value === "SALE" ? undefined : transactionMode.value));
	}

	function showCompleted({ invoice = null, payment = null, mode = null, extra = null } = {}) {
		if (!isEnabled.value) return;
		clearTimeout(thankYouTimer);
		if (payment) setPayment({ ...payment, is_open: true });
		paymentActive.value = false;
		const transactionType = String(mode || transactionMode.value || "SALE").toUpperCase();
		const payload = buildCartPayload(
			transactionType === "RETURN" ? "RETURN" : transactionType === "EXCHANGE" ? "EXCHANGE" : "THANK_YOU"
		);
		if (invoice && typeof invoice === "object") {
			if ((!payload.items || payload.items.length === 0) && Array.isArray(invoice.items)) {
				payload.items = invoice.items.map(serializeItem);
				payload.current_item = payload.items[payload.items.length - 1] || null;
				payload.totals.quantity = payload.items.reduce((sum, item) => sum + Math.abs(number(item.quantity)), 0);
			}
			const invoiceTotal = number(invoice.grand_total ?? invoice.rounded_total ?? invoice.total);
			if (invoiceTotal) payload.totals.grand_total = Math.abs(invoiceTotal);
		}
		payload.transaction = {
			type: transactionType,
			invoice_number: invoice?.name || invoice?.sales_invoice || (typeof invoice === "string" ? invoice : ""),
			...(extra || {}),
		};
		publish(payload);

		const completedInvoiceName = payload.transaction?.invoice_number || "";
		const completedCustomer = customerKey();
		const completedCompany = shiftStore.profileCompany || shiftStore.currentProfile?.company || "";
		if (transactionType === "SALE" && completedInvoiceName && completedCustomer && completedCompany) {
			refreshCompletedWallet(completedInvoiceName, completedCustomer, completedCompany);
		}

		const duration = payload.thank_you?.duration || 5;
		completedHoldUntil = Date.now() + duration * 1000;
		thankYouTimer = setTimeout(() => {
			thankYouTimer = null;
			completedHoldUntil = 0;
			paymentSnapshot.value = null;
			paymentActive.value = false;
			paymentCustomerCredit.value = null;
			completedWalletAdded.value = 0;
			transactionMode.value = "SALE";

			if ((cartStore.invoiceItems || []).length > 0) {
				publish(buildCartPayload("CART"));
				return;
			}
			publish(basePayload("IDLE"));
		}, duration * 1000);
	}

	function clearToIdle() {
		clearTimeout(thankYouTimer);
		thankYouTimer = null;
		completedHoldUntil = 0;
		paymentSnapshot.value = null;
		paymentActive.value = false;
		paymentCustomerCredit.value = null;
		completedWalletAdded.value = 0;
		transactionMode.value = "SALE";
		if (isEnabled.value) publish(basePayload("IDLE"));
	}

	async function refreshTerminalBinding() {
		if (!initialized.value || !posProfile.value) return;
		const identity = await resolveTerminalIdentity(posProfile.value);
		const nextTerminalId = String(identity?.terminalId || "").trim();
		if (!nextTerminalId || nextTerminalId === terminalId.value) {
			terminalSource.value = identity?.source || terminalSource.value;
			return;
		}

		try { channel?.close(); } catch (_) {}
		terminalId.value = nextTerminalId;
		terminalSource.value = identity?.source || "terminal-setup";
		try {
			channel = "BroadcastChannel" in window ? new BroadcastChannel(channelName()) : null;
		} catch (_) {
			channel = null;
		}
		syncCartNow();
	}

	async function initialize(profile) {
		const normalized = String(profile || cartStore.posProfile || "").trim();
		if (!normalized) return false;
		if (initialized.value && posProfile.value === normalized) {
			syncCartNow();
			return true;
		}
		stop();
		posProfile.value = normalized;
		const identity = await resolveTerminalIdentity(normalized);
		terminalId.value = identity.terminalId;
		terminalSource.value = identity.source;
		try {
			if ("BroadcastChannel" in window) channel = new BroadcastChannel(channelName());
		} catch (_) {
			channel = null;
		}
		initialized.value = true;
		terminalChangeHandler = () => { refreshTerminalBinding(); };
		window.addEventListener(PRINT_PROVIDER_CHANGED_EVENT, terminalChangeHandler);
		stopCartWatch = watch(
			() => ({
				items: (cartStore.invoiceItems || []).map((item) => [
					item.item_code,
					item.quantity,
					item.rate,
					item.price_list_rate,
					item.discount_amount,
					item.discount_percentage,
				]),
				customer: cartStore.customer,
				subtotal: cartStore.subtotal,
				discount: cartStore.totalDiscount,
				grandTotal: cartStore.grandTotal,
				settings: settingsStore.settings,
			}),
			scheduleCartSync,
			{ deep: true, immediate: true }
		);
		stopCustomerFinancialWatch = watch(
			() => customerKey(cartStore.customer),
			() => refreshCustomerFinancials(cartStore.customer),
			{ immediate: true }
		);
		return true;
	}

	function stop() {
		clearTimeout(syncTimer);
		clearTimeout(thankYouTimer);
		thankYouTimer = null;
		completedHoldUntil = 0;
		if (stopCartWatch) stopCartWatch();
		stopCartWatch = null;
		if (stopCustomerFinancialWatch) stopCustomerFinancialWatch();
		stopCustomerFinancialWatch = null;
		customerFinancialKey.value = "";
		customerCreditBalance.value = null;
		customerWalletBalance.value = null;
		customerWalletProgram.value = "";
		customerWalletEnabled.value = false;
		completedWalletAdded.value = 0;
		if (terminalChangeHandler) window.removeEventListener(PRINT_PROVIDER_CHANGED_EVENT, terminalChangeHandler);
		terminalChangeHandler = null;
		try { channel?.close(); } catch (_) {}
		channel = null;
		initialized.value = false;
		previouslySeenQuantities = new Map();
		latestScannedKey = "";
		latestQuantityDelta = 0;
	}

	function getDisplayUrl() {
		const profile = encodeURIComponent(posProfile.value || cartStore.posProfile || "");
		const terminal = encodeURIComponent(terminalId.value || "");
		return `/pos/customer-display?profile=${profile}&terminal=${terminal}`;
	}

	async function openDisplayWindow({ preferSecondary = true } = {}) {
		if (!isEnabled.value || typeof window === "undefined") return null;
		const url = getDisplayUrl();
		const name = `POSNextCustomerDisplay_${posProfile.value || "POS"}_${terminalId.value || "terminal"}`.replace(/[^a-zA-Z0-9_-]/g, "_");
		let left = Number(window.screen?.availLeft || 0);
		let top = Number(window.screen?.availTop || 0);
		let width = Number(window.screen?.availWidth || window.screen?.width || 1280);
		let height = Number(window.screen?.availHeight || window.screen?.height || 720);

		if (preferSecondary) {
			try {
				if (typeof window.getScreenDetails === "function") {
					const details = await window.getScreenDetails();
					const secondary = details?.screens?.find((screen) => !screen.isPrimary) || null;
					if (secondary) {
						left = secondary.availLeft ?? secondary.left ?? left;
						top = secondary.availTop ?? secondary.top ?? top;
						width = secondary.availWidth ?? secondary.width ?? width;
						height = secondary.availHeight ?? secondary.height ?? height;
					}
				} else if (Number(window.screen?.availWidth || 0) > 0) {
					left = Number(window.screen?.availLeft || 0) + Number(window.screen?.availWidth || window.screen?.width || 0);
				}
			} catch (_) {}
		}

		const features = `popup=yes,left=${Math.round(left)},top=${Math.round(top)},width=${Math.round(width)},height=${Math.round(height)}`;
		let displayWindow = null;
		try { displayWindow = window.open(url, name, features); } catch (_) {}
		try { displayWindow?.focus(); } catch (_) {}
		return displayWindow;
	}

	return {
		state,
		posProfile,
		terminalId,
		terminalSource,
		initialized,
		isEnabled,
		initialize,
		stop,
		setPayment,
		setTransactionMode,
		showCompleted,
		clearToIdle,
		syncCartNow,
		scheduleCartSync,
		refreshCustomerFinancials,
		getDisplayUrl,
		openDisplayWindow,
	};
});
