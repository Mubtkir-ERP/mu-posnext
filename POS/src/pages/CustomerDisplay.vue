<template>
	<div :class="['customer-display', `theme-${theme.toLowerCase()}`, { 'is-compact': compactDisplay }]">
		<div v-if="!profile" class="empty-state">
			<h1>Customer Display</h1>
			<p>Missing POS Profile.</p>
		</div>

		<div v-else-if="!displayEnabled" class="empty-state">
			<h1>Customer Display Disabled</h1>
			<p>Enable Customer Display in POS Settings for {{ profile }}.</p>
		</div>

		<template v-else>
			<header class="display-header">
				<div class="brand-header">
					<img
						v-if="displayState?.company?.logo"
						:src="displayState.company.logo"
						class="company-logo"
						alt="Company logo"
					/>
					<div class="brand-copy">
						<div v-if="visible('company_name')" class="company-name">
							{{ displayState?.company?.name || "" }}
						</div>
						<div class="terminal-meta">
							<span v-if="visible('pos_location') && displayState?.company?.location">
								{{ displayState.company.location }}
							</span>
							<span v-if="visible('pos_number') && displayState?.company?.pos_number">
								{{ displayState.company.pos_number }}
							</span>
						</div>
					</div>
				</div>
				<div class="header-status">
					<div class="display-clock">{{ currentDateTime }}</div>
					<div class="status-pill" :class="{ online: connected }">
						<span class="status-dot"></span>
						{{ connected ? "Live" : "Waiting" }}
					</div>
				</div>
			</header>

			<main class="display-main">
				<section v-if="mode === 'IDLE'" class="idle-screen">
					<video
						v-if="idleMode === 'Video' && displayState?.idle?.video"
						:src="displayState.idle.video"
						class="idle-media"
						autoplay
						muted
						loop
						playsinline
					></video>
					<img
						v-else-if="idleMode === 'Image' && displayState?.idle?.image"
						:src="displayState.idle.image"
						class="idle-media"
						alt="Promotion"
					/>
					<div v-else class="welcome-panel">
						<div class="welcome-kicker">WELCOME</div>
						<h1 v-if="visible('company_name')">{{ displayState?.company?.name }}</h1>
						<p v-if="visible('welcome_text')">{{ displayState?.company?.welcome_text }}</p>
					</div>
                    <div v-if="showIdleOverlay" :class="['idle-overlay', `overlay-${overlayPosition.toLowerCase()}`]" :style="overlayContainerStyle" aria-live="off">
                        <div v-if="overlayStyle === 'Scrolling'" class="idle-overlay-marquee">
                            <span :key="`${idleMode}:${overlayMessage}`" class="idle-overlay-scroll" :style="overlayScrollingStyle">{{ overlayMessage }}</span>
                        </div>
                        <div v-else class="idle-overlay-static">{{ overlayMessage }}</div>
                    </div>
				</section>

				<section v-else-if="mode === 'THANK_YOU'" class="message-screen">
					<div class="message-icon">✓</div>
					<h1>{{ displayState?.thank_you?.title || "Thank You" }}</h1>
					<p>{{ displayState?.thank_you?.message }}</p>
					<div v-if="visible('invoice_number') && displayState?.transaction?.invoice_number" class="invoice-number">
						{{ displayState.transaction.invoice_number }}
					</div>
					<LoyaltyWalletSummary :state="displayState" :currency="currencyLabel" />
					<PaymentSummary :state="displayState" :currency="currencyLabel" />
				</section>

				<section v-else-if="mode === 'RETURN' || mode === 'EXCHANGE'" class="message-screen return-screen">
					<div class="mode-badge">{{ mode }}</div>
					<h1>{{ mode === 'RETURN' ? 'Return / Refund' : 'Exchange' }}</h1>
					<p v-if="displayState?.transaction?.invoice_number && visible('invoice_number')">
						{{ displayState.transaction.invoice_number }}
					</p>
					<CartSummary :state="displayState" :currency="currencyLabel" compact />
					<PaymentSummary :state="displayState" :currency="currencyLabel" />
				</section>

				<section v-else class="sale-screen redesigned-sale">
					<div class="cart-main-panel">
						<div class="cart-panel-header">
							<div>
								<div class="cart-panel-kicker">CART ITEMS</div>
								<div class="cart-panel-title">Your Items</div>
							</div>
							<div class="cart-count-badge">{{ displayState?.items?.length || 0 }} Items · {{ formatQty(displayState?.totals?.quantity || 0) }} Qty</div>
						</div>

						<div v-if="displayState?.items?.length" class="cart-history-large">
							<div class="cart-history-scroll pos-cart-style">
								<div
									v-for="(item, index) in displayState.items"
									:key="`${item.item_code || item.item_name}-${index}`"
									:class="['cart-line', 'pos-cart-line', { latest: index === highlightedCartIndex }]"
								>
									<div class="cart-line-item">
										<img v-if="visible('product_image') && item.image" :src="item.image" class="cart-line-image" alt="" />
										<div v-else-if="visible('product_image')" class="cart-line-image placeholder">No Image</div>
										<div class="cart-line-copy">
											<strong v-if="visible('item_name')">{{ item.item_name || item.item_code }}</strong>
											<strong v-else>{{ item.item_code }}</strong>
											<small v-if="visible('barcode') && item.barcode" class="cart-line-meta">{{ item.barcode }}</small>
										</div>
									</div>
									<div class="cart-line-math">
										<div v-if="visible('final_price')" class="cart-math-price"><small>UNIT PRICE</small><strong>{{ money(item.final_price) }}</strong></div>
										<div v-if="visible('quantity')" class="cart-math-qty"><small>QTY</small><strong>× {{ formatQty(item.quantity) }}</strong></div>
										<div v-if="visible('final_price')" class="cart-math-amount"><small>AMOUNT</small><strong>{{ money(item.line_total ?? (Number(item.final_price || 0) * Number(item.quantity || 0))) }}</strong></div>
									</div>
								</div>
							</div>
						</div>
						<div v-else class="cart-empty">Ready for the next item</div>

						<CartSummary :state="displayState" :currency="currencyLabel" />
					</div>

					<aside class="sale-sidebar">
						<div v-if="displayState?.current_item" class="current-item-card" :class="{ 'without-image': !showProductImage }">
							<div v-if="showProductImage" class="current-item-image-wrap">
								<img v-if="displayState.current_item.image" :src="displayState.current_item.image" class="current-item-image" alt="Product" />
								<div v-else class="image-placeholder compact">No Image</div>
							</div>
							<div class="current-item-copy">
								<div class="card-title">LATEST ITEM</div>
								<h2
								v-if="visible('item_name')"
								class="latest-item-name"
								:style="latestItemTitleStyle(displayState.current_item.item_name || displayState.current_item.item_code)"
							>
								{{ displayState.current_item.item_name || displayState.current_item.item_code }}
							</h2>
								<div v-if="visible('barcode') && displayState.current_item.barcode" class="barcode compact">{{ displayState.current_item.barcode }}</div>
								<div v-if="visible('quantity')" class="latest-item-quantity-grid">
									<div v-if="Number(displayState.latest_quantity_delta || 0) !== 0" class="latest-qty-tile" :class="Number(displayState.latest_quantity_delta) < 0 ? 'removed' : 'added'">
										<span>{{ Number(displayState.latest_quantity_delta) < 0 ? 'REMOVED' : 'JUST ADDED' }}</span>
										<strong>{{ Number(displayState.latest_quantity_delta) > 0 ? '+' : '−' }}{{ formatQty(Math.abs(Number(displayState.latest_quantity_delta))) }}</strong>
									</div>
									<div class="latest-qty-tile in-cart">
										<span>TOTAL IN CART</span>
										<strong>{{ formatQty(displayState.current_item.quantity) }}</strong>
									</div>
								</div>
								<div class="current-item-prices">
									<div v-if="visible('original_price')" class="original"><span>ORIGINAL PRICE</span><strong>{{ money(displayState.current_item.original_price) }}</strong></div>
									<div v-if="visible('discount_amount') && displayState.current_item.discount_amount > 0" class="discount"><span>Discount</span><strong>-{{ money(displayState.current_item.discount_amount) }}</strong></div>
									<div v-if="visible('final_price')" :class="['final', { discounted: Number(displayState.current_item.discount_amount || 0) > 0 }]"><span>FINAL PRICE</span><strong>{{ money(displayState.current_item.final_price) }}</strong></div>
								</div>
							</div>
						</div>

						<div v-if="hasCustomerInfo" class="customer-card">
							<div v-if="visible('customer_name') && displayState?.customer?.name">
								<span>Customer</span><strong>{{ displayState.customer.name }}</strong>
							</div>
							<div v-if="visible('loyalty_points') && displayState?.customer?.loyalty_program">
								<span>Loyalty Program</span><strong>{{ displayState.customer.loyalty_program }}</strong>
							</div>
							<div v-if="visible('loyalty_points') && displayState?.customer?.wallet_balance !== null">
								<span>Loyalty Wallet Balance</span><strong>{{ money(displayState.customer.wallet_balance) }}</strong>
							</div>
							<div v-if="mode === 'PAYMENT' && visible('loyalty_points') && Number(displayState?.customer?.wallet_used || 0) > 0">
								<span>Wallet Used</span><strong>{{ money(displayState.customer.wallet_used) }}</strong>
							</div>
							<div v-if="visible('customer_credit') && displayState?.customer?.credit !== null">
								<span>Customer Credit</span><strong>{{ money(displayState.customer.credit) }}</strong>
							</div>
						</div>

						<PaymentSummary v-if="mode === 'PAYMENT'" :state="displayState" :currency="currencyLabel" />
					</aside>
				</section>
			</main>

			<button class="fullscreen-button" @click="toggleFullscreen">⛶</button>
		</template>
	</div>
</template>

<script setup>
import { computed, defineComponent, h, nextTick, onMounted, onUnmounted, ref } from "vue";
import { useRoute } from "vue-router";
import { usePOSSettingsStore } from "@/stores/posSettings";
import { resolveTerminalIdentity } from "@/utils/terminalIdentity";

const STORAGE_PREFIX = "posnext_customer_display_state_v1";
const CHANNEL_PREFIX = "posnext-customer-display-v1";
const route = useRoute();
const settingsStore = usePOSSettingsStore();
const profile = computed(() => String(route.query.profile || "").trim());
const terminalId = ref(String(route.query.terminal || "").trim());
const displayState = ref(null);
const highlightedCartIndex = ref(-1);
let cartHighlightTimer = null;
const connected = ref(false);
const now = ref(new Date());
// Display-only viewport tracking. The cashier and normalized display payload are unchanged.
const viewportSize = ref({ width: typeof window !== 'undefined' ? window.innerWidth : 1280, height: typeof window !== 'undefined' ? window.innerHeight : 800 });
const updateViewportSize = () => { viewportSize.value = { width: window.innerWidth, height: window.innerHeight }; };
let channel = null;
let staleTimer = null;
let clockTimer = null;

const currentDateTime = computed(() => {
	try {
		return new Intl.DateTimeFormat(undefined, {
			year: "numeric",
			month: "short",
			day: "2-digit",
			hour: "2-digit",
			minute: "2-digit",
			second: "2-digit",
		}).format(now.value);
	} catch (_) {
		return now.value.toLocaleString();
	}
});

const displayEnabled = computed(() => Boolean(Number(settingsStore.settings.customer_display_enabled || 0)));
const mode = computed(() => displayState.value?.mode || "IDLE");
const idleMode = computed(() => displayState.value?.idle?.mode || "Welcome");
const theme = computed(() => settingsStore.settings.customer_display_theme || "Dark");
const compactDisplay = computed(() => {
    const preference = String(settingsStore.settings.customer_display_size_mode || 'Auto');
    if (preference === 'Compact') return true;
    if (preference === 'Standard') return false;
    // Viewport pixels (not physical panel resolution): landscape 7-inch / small-screen displays.
    return viewportSize.value.width <= 1100 && viewportSize.value.height <= 720 && viewportSize.value.width >= 680;
});
const currencyLabel = computed(() => settingsStore.settings.customer_display_currency_label || "KD");

// Display-only overlay. It never changes cashier, cart, payment or recovery state.
const overlayMessage = computed(() => String(settingsStore.settings.customer_display_overlay_text || '').slice(0, 500).trim());
const overlayStyle = computed(() => settingsStore.settings.customer_display_overlay_type === 'Scrolling' ? 'Scrolling' : 'Static');
const overlayPosition = computed(() => ['Top','Center','Bottom'].includes(settingsStore.settings.customer_display_overlay_position) ? settingsStore.settings.customer_display_overlay_position : 'Bottom');
const showIdleOverlay = computed(() => {
    if (mode.value !== 'IDLE' || !Boolean(Number(settingsStore.settings.customer_display_overlay_enabled || 0)) || !overlayMessage.value) return false;
    const target = String(settingsStore.settings.customer_display_overlay_on || 'All');
    return target === 'All' || target === idleMode.value;
});
const clampNumber = (v, fallback, min, max) => Math.max(min, Math.min(max, Number.isFinite(Number(v)) ? Number(v) : fallback));
const overlayContainerStyle = computed(() => {
    const textColor = /^#[0-9a-fA-F]{6}$/.test(String(settingsStore.settings.customer_display_overlay_text_color || '')) ? settingsStore.settings.customer_display_overlay_text_color : '#FFFFFF';
    const bg = /^#[0-9a-fA-F]{6}$/.test(String(settingsStore.settings.customer_display_overlay_background_color || '')) ? settingsStore.settings.customer_display_overlay_background_color : '#000000';
    const opacity = clampNumber(settingsStore.settings.customer_display_overlay_opacity, 65, 0, 100) / 100;
    return {
        color: textColor,
        backgroundColor: `rgba(${parseInt(bg.slice(1,3),16)}, ${parseInt(bg.slice(3,5),16)}, ${parseInt(bg.slice(5,7),16)}, ${opacity})`,
        fontSize: `${clampNumber(settingsStore.settings.customer_display_overlay_font_size, 28, 14, 72)}px`
    };
});
const overlayScrollingStyle = computed(() => ({ animationDuration: ({Slow:'35s', Normal:'20s', Fast:'11s'})[settingsStore.settings.customer_display_overlay_scroll_speed] || '20s' }));

const showProductImage = computed(() => visible("product_image") && !!displayState.value?.current_item);
const hasCustomerInfo = computed(() => {
	const c = displayState.value?.customer;
	return !!(c && (c.name || c.loyalty_program || c.wallet_balance !== null || c.credit !== null));
});

function visible(key) {
	return displayState.value?.visibility?.[key] !== false;
}
function money(value) {
	return `${currencyLabel.value} ${Number(value || 0).toFixed(3)}`;
}
function formatQty(value) {
	const n = Number(value || 0);
	return Number.isInteger(n) ? String(n) : n.toFixed(3).replace(/0+$/, "").replace(/\.$/, "");
}

function latestItemTitleStyle(value) {
	const length = String(value || "").trim().length;
	let size = 26;
	if (length > 18) size = 23;
	if (length > 26) size = 20;
	if (length > 36) size = 17;
	if (length > 48) size = 15;
	return { fontSize: `${size}px` };
}

function paymentTileStyle(type, state) {
	const light = String(state?.theme || "").toLowerCase() === "light";
	if (type === "paid") {
		return light
			? { background: "#eaf4ff", border: "1px solid #cfe7ff", color: "#0877d1" }
			: { background: "rgba(38,139,255,.18)", border: "1px solid rgba(88,169,255,.35)", color: "#58a9ff" };
	}
	if (type === "change") {
		return light
			? { background: "#ebfaef", border: "1px solid #c9efd5", color: "#18894a" }
			: { background: "rgba(46,204,113,.18)", border: "1px solid rgba(85,217,138,.35)", color: "#55d98a" };
	}
	return light
		? { background: "#fff3e6", border: "1px solid #ffd8ad", color: "#b96500" }
		: { background: "rgba(255,159,67,.18)", border: "1px solid rgba(255,177,95,.35)", color: "#ffb15f" };
}

function markLive() {
	connected.value = true;
	clearTimeout(staleTimer);
	staleTimer = setTimeout(() => (connected.value = false), 15000);
}
async function applyState(payload) {
    if (!payload || typeof payload !== "object") return;

    displayState.value = payload;
    markLive();

    const latestIndex = Number(payload.latest_item_index);
    const quantityDelta = Number(payload.latest_quantity_delta || 0);

    if (
            quantityDelta !== 0 &&
            Number.isInteger(latestIndex) &&
            latestIndex >= 0
    ) {
            highlightedCartIndex.value = latestIndex;

            await nextTick();

            const rows = document.querySelectorAll(
                    ".cart-history-scroll .cart-line"
            );

            const row = rows[latestIndex];

            if (row) {
                    row.scrollIntoView({
                            behavior: "smooth",
                            block: "nearest",
                            inline: "nearest",
                    });
            }

            clearTimeout(cartHighlightTimer);

            cartHighlightTimer = setTimeout(() => {
                    highlightedCartIndex.value = -1;
            }, 1200);
    }
}
function readSnapshot() {
	try {
		const raw = localStorage.getItem(`${STORAGE_PREFIX}:${profile.value}:${terminalId.value || "unassigned"}`);
		if (raw) applyState(JSON.parse(raw));
	} catch (_) {}
}
function handleStorage(event) {
	if (event.key !== `${STORAGE_PREFIX}:${profile.value}:${terminalId.value || "unassigned"}` || !event.newValue) return;
	try { applyState(JSON.parse(event.newValue)); } catch (_) {}
}
async function toggleFullscreen() {
	try {
		if (!document.fullscreenElement) await document.documentElement.requestFullscreen();
		else await document.exitFullscreen();
	} catch (_) {}
}

const CartSummary = defineComponent({
	props: { state: Object, currency: String, compact: Boolean },
	setup(props) {
		const fmt = (v) => `${props.currency || ""} ${Number(v || 0).toFixed(3)}`.trim();
		const fmtQty = (value) => { const n = Number(value || 0); return Number.isInteger(n) ? String(n) : n.toFixed(3).replace(/0+$/, "").replace(/\.$/, ""); };
		return () => {
			const v = props.state?.visibility || {};
			const t = props.state?.totals || {};
			const rows = [];
			rows.push(["Total Items", Array.isArray(props.state?.items) ? props.state.items.length : 0, "items"]);
			if (v.running_qty !== false) rows.push(["Total Qty", fmtQty(t.quantity), "qty"]);
			if (!props.compact && v.subtotal !== false) rows.push(["Subtotal", fmt(t.subtotal), "subtotal"]);
			if (!props.compact && v.total_discount !== false && Number(t.discount || 0) > 0) rows.push(["Discount", `-${fmt(t.discount)}`, "discount"]);
			if (v.grand_total !== false) rows.push(["Grand Total", fmt(t.grand_total), "grand"]);
			return h("div", { class: ["totals-card", props.compact ? "compact" : "summary-strip"] }, rows.map(([label, value, type]) =>
				h("div", { class: ["summary-tile", type] }, [h("span", label), h("strong", String(value))])
			));
		};
	},
});

const LoyaltyWalletSummary = defineComponent({
	props: { state: Object, currency: String },
	setup(props) {
		const fmt = (v) => `${props.currency || ""} ${Number(v || 0).toFixed(3)}`.trim();
		return () => {
			const c = props.state?.customer || {};
			const p = props.state?.payment || {};
			const program = c.loyalty_program || p.loyalty_program || "";
			const used = Number(c.wallet_used ?? p.wallet_used ?? 0);
			const added = Number(c.wallet_added ?? p.wallet_added ?? 0);
			const balance = c.wallet_balance ?? p.wallet_balance;
			if (!program && used <= 0 && added <= 0 && (balance === null || balance === undefined)) return null;

			const rows = [];
			if (program) rows.push(["Loyalty Program", program]);
			if (used > 0) rows.push(["Wallet Used", fmt(used)]);
			if (added > 0) rows.push(["Wallet Added", fmt(added)]);
			if (balance !== null && balance !== undefined) rows.push(["Wallet Balance", fmt(balance)]);

			return h("div", { class: "loyalty-wallet-card" }, [
				h("div", { class: "card-title" }, "Loyalty Wallet"),
				...rows.map(([label, value]) => h("div", { class: "loyalty-wallet-row" }, [h("span", label), h("strong", value)])),
			]);
		};
	},
});

const PaymentSummary = defineComponent({
	props: { state: Object, currency: String },
	setup(props) {
		const fmt = (v) => `${props.currency || ""} ${Number(v || 0).toFixed(3)}`.trim();
		return () => {
			const p = props.state?.payment;
			if (!p) return null;
			const v = props.state?.visibility || {};
			const methodRows = v.payment_method !== false ? (p.methods || []).filter((m) => Number(m.amount || 0) !== 0) : [];
			const tiles = [];
			if (v.amount_paid !== false) tiles.push(["Paid", fmt(p.paid_amount), "paid"]);
			if (v.remaining_balance !== false && Number(p.remaining_balance || 0) > 0) tiles.push(["Remaining", fmt(p.remaining_balance), "remaining"]);
			if (v.change !== false && Number(p.change_amount || 0) > 0) tiles.push(["Change Due", fmt(p.change_amount), "change"]);
			if (!methodRows.length && !tiles.length) return null;
			return h("div", { class: "payment-card payment-card-redesigned" }, [
				h("div", { class: "card-title" }, "Payment"),
				methodRows.length ? h("div", { class: "payment-methods" }, methodRows.map((m) => h("div", { class: "payment-method-row" }, [h("span", m.mode_of_payment || "Payment"), h("strong", fmt(m.amount))]))) : null,
				tiles.length ? h("div", { class: "payment-tiles" }, tiles.map(([label, value, type]) => h("div", { class: ["payment-tile", type], style: paymentTileStyle(type, props.state) }, [h("span", label), h("strong", value)]))) : null,
			]);
		};
	},
});

onUnmounted(() => {
        clearTimeout(cartHighlightTimer);
});

onMounted(async () => {
    updateViewportSize();
    window.addEventListener('resize', updateViewportSize, { passive: true });
	clockTimer = setInterval(() => {
		now.value = new Date();
	}, 1000);
	if (profile.value) {
		await settingsStore.loadSettings(profile.value);
		if (!terminalId.value) {
			const identity = await resolveTerminalIdentity(profile.value);
			terminalId.value = identity.terminalId;
		}
		readSnapshot();
		window.addEventListener("storage", handleStorage);
		try {
			if ("BroadcastChannel" in window) {
				channel = new BroadcastChannel(`${CHANNEL_PREFIX}:${profile.value}:${terminalId.value || "unassigned"}`);
				channel.onmessage = (event) => {
					if (!event.data?.terminal_id || event.data.terminal_id === terminalId.value) applyState(event.data);
				};
			}
		} catch (_) {}
	}
});

onUnmounted(() => {
    window.removeEventListener('resize', updateViewportSize);
	window.removeEventListener("storage", handleStorage);
	clearTimeout(staleTimer);
	clearInterval(clockTimer);
	try { channel?.close(); } catch (_) {}
});
</script>

<style>
.customer-display { min-height:100vh; width:100vw; overflow:hidden; font-family:Inter,Arial,sans-serif; background:#0b0b0c; color:#fff; display:flex; flex-direction:column; }
.theme-light { background:#f7f7f5; color:#111; }
.display-header { height:82px; padding:18px 32px; display:flex; align-items:center; justify-content:space-between; border-bottom:1px solid rgba(255,255,255,.12); background:rgba(0,0,0,.18); }
.theme-light .display-header { border-color:#ddd; background:#fff; }
.brand-header{display:flex;align-items:center;gap:12px;min-width:0}.company-logo{width:46px;height:46px;object-fit:contain;border-radius:8px;flex:none}.brand-copy{min-width:0}.company-name { font-size:26px; font-weight:800; letter-spacing:-.03em; }
.terminal-meta { display:flex; gap:14px; margin-top:3px; opacity:.65; font-size:13px; }
.header-status{display:flex;align-items:center;gap:14px}.display-clock{font-size:13px;font-weight:650;letter-spacing:.02em;opacity:.72;white-space:nowrap}.status-pill { display:flex; align-items:center; gap:8px; padding:7px 12px; border-radius:999px; background:rgba(255,255,255,.08); font-size:12px; font-weight:700; }
.status-dot { width:8px; height:8px; border-radius:50%; background:#777; }.status-pill.online .status-dot{background:#2ecc71;box-shadow:0 0 12px #2ecc71}
.display-main { flex:1; min-height:0; }
.idle-screen,.message-screen { height:calc(100vh - 82px); display:flex; align-items:center; justify-content:center; position:relative; text-align:center; }
.idle-media { width:100%; height:100%; object-fit:cover; }
.welcome-panel h1,.message-screen h1 { font-size:clamp(52px,7vw,112px); margin:10px 0; letter-spacing:-.05em; }
.welcome-panel p,.message-screen>p { font-size:clamp(20px,2vw,34px); opacity:.7; margin:0; }
.welcome-kicker,.mode-badge { font-size:15px; font-weight:800; letter-spacing:.22em; opacity:.55; }
.message-screen { flex-direction:column; gap:12px; padding:40px; }.message-icon{width:86px;height:86px;border-radius:50%;background:#fff;color:#111;display:flex;align-items:center;justify-content:center;font-size:48px;font-weight:900}
.invoice-number{padding:10px 16px;border:1px solid rgba(255,255,255,.2);border-radius:10px;font-weight:700;opacity:.8}

.redesigned-sale { height:calc(100vh - 82px); display:grid; grid-template-columns:minmax(0,1.72fr) minmax(360px,.72fr); min-height:0; }
.cart-main-panel { min-width:0; min-height:0; padding:30px 32px 26px; display:flex; flex-direction:column; gap:18px; }
.cart-panel-header { display:flex; align-items:center; justify-content:space-between; gap:20px; flex:none; }
.cart-panel-kicker,.card-title{font-size:12px;font-weight:900;letter-spacing:.14em;opacity:.5}.cart-panel-title{font-size:28px;font-weight:800;letter-spacing:-.03em;margin-top:3px}.cart-count-badge{padding:9px 14px;border-radius:999px;background:rgba(255,255,255,.08);font-weight:800;font-size:14px}
.cart-history-large { min-height:0; flex:1; border:1px solid rgba(255,255,255,.13); border-radius:18px; background:rgba(255,255,255,.025); overflow:hidden; display:flex; flex-direction:column; }
.cart-history-scroll{overflow:auto;min-height:0;padding:10px;display:flex;flex-direction:column;gap:8px}
.cart-line{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:16px;align-items:center;padding:10px 12px;border:1px solid rgba(255,255,255,.08);border-radius:12px;background:rgba(255,255,255,.025);transition:.18s ease}.cart-line.latest{background:rgba(46,204,113,.11);border-color:rgba(46,204,113,.26);box-shadow:inset 4px 0 0 #2ecc71}.cart-line-item{display:flex;align-items:center;gap:12px;min-width:0}.cart-line-image{width:54px;height:54px;object-fit:contain;background:#fff;border-radius:10px;flex:none;border:1px solid rgba(0,0,0,.06)}.cart-line-image.placeholder{display:flex;align-items:center;justify-content:center;color:#999;font-size:8px;font-weight:700}.cart-line-copy{min-width:0;display:flex;flex-direction:column;gap:5px}.cart-line-copy strong{font-size:16px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.cart-line-meta{display:flex;gap:10px;align-items:center;opacity:.56;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:12px}.cart-line-price{text-align:right;white-space:nowrap;font-size:18px;color:#1683e8}.cart-empty{flex:1;display:flex;align-items:center;justify-content:center;opacity:.45;font-size:24px}
.sale-sidebar { min-height:0; overflow:auto; border-left:1px solid rgba(255,255,255,.12); background:rgba(255,255,255,.035); padding:22px; display:flex; flex-direction:column; gap:16px; }
.current-item-card,.customer-card,.totals-card,.payment-card { border:1px solid rgba(255,255,255,.14); border-radius:18px; background:rgba(0,0,0,.14); }
.current-item-card{padding:16px;display:grid;grid-template-columns:132px minmax(0,1fr);gap:16px;align-items:center}.current-item-image-wrap{width:132px;height:132px;border-radius:14px;overflow:hidden;background:#fff;display:flex;align-items:center;justify-content:center}.current-item-image{width:100%;height:100%;object-fit:contain}.image-placeholder.compact{color:#999;font-size:11px;font-weight:700}.current-item-copy{min-width:0}.current-item-copy h2{line-height:1.08;margin:5px 0 8px;letter-spacing:-.035em}.latest-item-name{white-space:normal;overflow:visible;text-overflow:clip;max-width:100%;display:block;overflow-wrap:anywhere;word-break:normal}.barcode.compact{font-size:12px;opacity:.5;margin-bottom:8px}.current-item-qty{font-size:15px;font-weight:800;margin-bottom:8px}.current-item-prices>div{display:flex;justify-content:space-between;gap:12px;padding:5px 0;font-size:13px}.current-item-prices span{opacity:.58}.current-item-prices .discount strong{color:#ff8a65}.current-item-prices .final{border-top:1px solid rgba(255,255,255,.1);margin-top:5px;padding-top:9px}.current-item-prices .final strong{font-size:19px}
.loyalty-wallet-card{width:min(620px,82vw);text-align:left;border:1px solid rgba(255,255,255,.14);border-radius:18px;background:rgba(0,0,0,.14);padding:15px 17px;box-sizing:border-box}.loyalty-wallet-card>.card-title{margin-bottom:6px}.loyalty-wallet-row{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:7px 0;font-size:14px}.loyalty-wallet-row span{opacity:.62}.loyalty-wallet-row strong{white-space:nowrap}.theme-light .loyalty-wallet-card{border-color:#ddd;background:#fff}
.customer-card{padding:15px 17px}.customer-card>div{display:flex;justify-content:space-between;gap:18px;padding:7px 0;font-size:14px}.customer-card span{opacity:.58}
.totals-card.summary-strip{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;background:transparent;border:0;padding:0}.summary-tile{min-width:0;border:1px solid rgba(255,255,255,.13);background:rgba(255,255,255,.045);border-radius:16px;padding:13px 16px;display:flex;flex-direction:column;gap:6px;box-shadow:0 8px 20px rgba(0,0,0,.08)}.summary-tile span{font-size:11px;opacity:.55;text-transform:uppercase;letter-spacing:.07em;white-space:nowrap}.summary-tile strong{font-size:21px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.summary-tile.grand{background:rgba(255,255,255,.09)}.summary-tile.grand strong{font-size:24px}.summary-tile.discount strong{color:#ff8a65}.totals-card.compact{padding:16px}.totals-card.compact .summary-tile{margin-bottom:8px}
.payment-card-redesigned{padding:16px;box-shadow:0 12px 28px rgba(0,0,0,.12)}.payment-card-redesigned>.card-title{margin-bottom:10px}.payment-methods{display:flex;flex-direction:column;gap:8px;margin-bottom:12px}.payment-method-row{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:10px 12px;border-radius:12px;background:rgba(255,255,255,.045);font-size:14px}.payment-method-row span{opacity:.68}.payment-method-row strong{white-space:nowrap;font-size:16px}.payment-tiles{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.payment-tile{min-height:96px;border-radius:18px;padding:14px 16px;display:flex;flex-direction:column;justify-content:center;gap:7px;text-align:center;border:1px solid transparent;box-shadow:0 10px 24px rgba(0,0,0,.14),inset 0 1px 0 rgba(255,255,255,.18)}.payment-tile span{font-size:11px;font-weight:900;text-transform:uppercase;letter-spacing:.08em;opacity:.76;white-space:nowrap}.payment-tile strong{font-size:24px;line-height:1.05;white-space:nowrap}.payment-tile.paid{background:linear-gradient(145deg,rgba(33,150,243,.24),rgba(33,150,243,.10));border-color:rgba(88,169,255,.42);color:#58a9ff}.payment-tile.change{background:linear-gradient(145deg,rgba(46,204,113,.24),rgba(46,204,113,.10));border-color:rgba(85,217,138,.42);color:#55d98a}.payment-tile.remaining{background:linear-gradient(145deg,rgba(255,159,67,.25),rgba(255,159,67,.10));border-color:rgba(255,177,95,.42);color:#ffb15f}.payment-tiles:has(.payment-tile:only-child){grid-template-columns:1fr}
.theme-light .cart-history-large,.theme-light .current-item-card,.theme-light .customer-card,.theme-light .payment-card{border-color:#ddd;background:#fff}.theme-light .sale-sidebar{border-color:#ddd;background:#fff}.theme-light .cart-line{border-color:#e8e8e8;background:#fff}.theme-light .cart-line.latest{background:#eafaf0;border-color:#c9ecd5}.theme-light .cart-count-badge{background:#eee}.theme-light .summary-tile{border-color:#ddd;background:#fff}.theme-light .summary-tile.grand{background:#f4f4f4}.theme-light .payment-card-redesigned{box-shadow:0 14px 34px rgba(17,24,39,.10)}.theme-light .payment-method-row{background:#f7f8fa}.theme-light .payment-tile{box-shadow:0 10px 24px rgba(17,24,39,.10),inset 0 1px 0 rgba(255,255,255,.95)}.theme-light .payment-tile.paid{background:linear-gradient(145deg,#eff8ff,#dceeff);border-color:#bcdfff;color:#0877d1}.theme-light .payment-tile.change{background:linear-gradient(145deg,#effcf3,#dbf5e4);border-color:#bce8ca;color:#18894a}.theme-light .payment-tile.remaining{background:linear-gradient(145deg,#fff8ee,#ffead2);border-color:#ffd3a2;color:#b96500}
.return-screen .totals-card,.message-screen .payment-card{width:min(620px,82vw);text-align:left}.message-screen .payment-tiles{grid-template-columns:repeat(2,minmax(0,1fr))}
.empty-state { min-height:100vh; display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center; }.empty-state h1{font-size:42px;margin:0 0 8px}.empty-state p{opacity:.65}
.fullscreen-button{position:fixed;right:16px;bottom:16px;width:44px;height:44px;border:0;border-radius:12px;background:rgba(255,255,255,.12);color:inherit;font-size:22px;cursor:pointer}
@media(max-width:1050px){.redesigned-sale{grid-template-columns:1fr}.sale-sidebar{border-left:0;border-top:1px solid rgba(255,255,255,.12)}.current-item-card{grid-template-columns:110px 1fr}.current-item-image-wrap{width:110px;height:110px}.totals-card.summary-strip{grid-template-columns:repeat(2,minmax(0,1fr))}.cart-main-panel{padding:20px}.display-header{padding:14px 20px;height:70px}.redesigned-sale,.idle-screen,.message-screen{height:calc(100vh - 70px)}}

/* Clearly separated price cards for the most recently scanned product. */
.current-item-prices{display:grid;gap:8px;margin-top:10px}
.current-item-prices>div{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:6px 12px;border:1px solid rgba(160,175,200,.22);border-radius:11px;padding:10px 12px;font-size:13px;background:rgba(125,140,160,.10)}
.current-item-prices>div span{opacity:1;font-weight:800;font-size:10px;letter-spacing:.055em}
.current-item-prices>div strong{font-size:16px;white-space:nowrap;font-variant-numeric:tabular-nums}
.current-item-prices .original{background:rgba(145,160,180,.10);border-color:rgba(145,160,180,.25);color:inherit}
.current-item-prices .final{background:rgba(33,150,243,.16);border-color:rgba(77,164,255,.38);color:#66b5ff;margin-top:0;padding:10px 12px}
.current-item-prices .final strong{font-size:20px;color:inherit}
.current-item-prices .final.discounted{background:rgba(40,177,103,.16);border-color:rgba(80,206,133,.38);color:#67dd9c}
.theme-light .current-item-prices .original{background:#f4f6f9;border-color:#e0e5ed;color:#475569}
.theme-light .current-item-prices .final{background:#eef7ff;border-color:#bfdefb;color:#136fc4}
.theme-light .current-item-prices .final.discounted{background:#ecfbf2;border-color:#b7e8c8;color:#158347}

/* Customer-facing quantity/price columns and color-coded totals. Layout-only update. */
.cart-line-math{display:grid;grid-template-columns:minmax(105px,1fr) minmax(55px,.55fr) minmax(135px,1.1fr);align-items:center;gap:12px;min-width:345px;text-align:right}
.cart-line-math>div{display:flex;flex-direction:column;gap:5px;min-width:0}
.cart-line-math small{font-size:10px;font-weight:800;letter-spacing:.09em;opacity:.52;white-space:nowrap}
.cart-line-math strong{font-size:16px;white-space:nowrap;font-variant-numeric:tabular-nums}
.cart-math-qty strong{font-size:19px}
.cart-math-amount strong{font-size:19px;color:#2387ec}
.cart-line-copy strong{white-space:normal;overflow:visible;text-overflow:clip;overflow-wrap:anywhere}
.totals-card.summary-strip{grid-template-columns:repeat(auto-fit,minmax(135px,1fr));gap:12px}
.summary-tile{box-shadow:0 9px 20px rgba(0,0,0,.12),inset 0 1px 0 rgba(255,255,255,.13)}
.summary-tile.items{background:linear-gradient(145deg,#31215c,#241d45);border-color:#7561ac;color:#ebe3ff}
.summary-tile.qty{background:linear-gradient(145deg,#063f40,#123137);border-color:#297d7f;color:#c5ffff}
.summary-tile.subtotal{background:linear-gradient(145deg,#183766,#152948);border-color:#426fa4;color:#dbeeff}
.summary-tile.discount{background:linear-gradient(145deg,#5d3524,#48281b);border-color:#aa664d;color:#ffe3cf}
.summary-tile.grand{background:linear-gradient(145deg,#16462d,#113324);border-color:#32895b;color:#dcffea}
.summary-tile.grand strong,.summary-tile.discount strong{color:inherit}
.theme-light .summary-tile.items{background:linear-gradient(145deg,#f3eeff,#e5dbff);border-color:#cdbdf4;color:#5636a0}
.theme-light .summary-tile.qty{background:linear-gradient(145deg,#e8fbf8,#d4f3ee);border-color:#9cdbd1;color:#076d65}
.theme-light .summary-tile.subtotal{background:linear-gradient(145deg,#eef6ff,#dcecff);border-color:#bbd8ff;color:#1763ad}
.theme-light .summary-tile.discount{background:linear-gradient(145deg,#fff4e9,#ffe7d5);border-color:#f5ccae;color:#ad5a25}
.theme-light .summary-tile.grand{background:linear-gradient(145deg,#eafbf0,#d3f1df);border-color:#a4dfbb;color:#167343}
.theme-light .summary-tile.grand strong,.theme-light .summary-tile.discount strong{color:inherit}
@media(max-width:760px){.cart-line{grid-template-columns:1fr}.cart-line-math{min-width:0;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px}.cart-line-math strong{font-size:13px}.cart-math-amount strong{font-size:15px}.totals-card.summary-strip{grid-template-columns:repeat(2,minmax(0,1fr))}}

/* When product images are disabled, reclaim the entire latest-item card width.
   Keep this rule after responsive styles so the empty image column never returns. */
.current-item-card.without-image {
    grid-template-columns: minmax(0, 1fr);
    align-items: stretch;
}
.current-item-card.without-image .current-item-copy {
    min-width: 0;
    width: 100%;
}
.current-item-card.without-image .latest-item-name {
    max-width: 100%;
    overflow-wrap: break-word;
    word-break: normal;
}
.current-item-card.without-image .current-item-prices {
    grid-template-columns: repeat(2, minmax(0, 1fr));
}
@media (max-width: 460px) {
    .current-item-card.without-image .current-item-prices {
        grid-template-columns: minmax(0, 1fr);
    }
}
/* The last barcode/quantity change is distinct from the cumulative cart quantity. */
.latest-item-quantity-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin:10px 0}
.latest-item-quantity-grid:has(.latest-qty-tile:only-child){grid-template-columns:1fr}
.latest-qty-tile{min-width:0;border:1px solid rgba(148,163,184,.24);border-radius:11px;padding:9px 11px;display:flex;flex-direction:column;gap:3px;background:rgba(148,163,184,.09)}
.latest-qty-tile span{font-size:9px;font-weight:800;letter-spacing:.055em;line-height:1.2}
.latest-qty-tile strong{font-size:19px;line-height:1.15;font-variant-numeric:tabular-nums}
.latest-qty-tile.added{background:rgba(59,130,246,.11);border-color:rgba(59,130,246,.3);color:#60a5fa}
.latest-qty-tile.removed{background:rgba(249,115,22,.11);border-color:rgba(249,115,22,.3);color:#fb923c}
.latest-qty-tile.in-cart{background:rgba(148,163,184,.09)}
.theme-light .latest-qty-tile.added{background:#eff6ff;border-color:#bfdbfe;color:#1d4ed8}
.theme-light .latest-qty-tile.removed{background:#fff7ed;border-color:#fed7aa;color:#c2410c}
.theme-light .latest-qty-tile.in-cart{background:#f8fafc;border-color:#e2e8f0;color:#334155}
@media(max-width:430px){.latest-item-quantity-grid{grid-template-columns:1fr}}

/* Customer Display idle overlays: isolated from checkout and Thank You screens. */
.idle-screen{position:relative;overflow:hidden}
.idle-overlay{position:absolute;z-index:5;left:0;right:0;min-height:58px;padding:13px clamp(16px,3vw,50px);display:flex;align-items:center;justify-content:center;text-align:center;line-height:1.25;font-weight:800;pointer-events:none;box-sizing:border-box;max-width:100%;overflow:hidden;white-space:pre-line;text-shadow:0 1px 3px rgba(0,0,0,.22)}
.idle-overlay.overlay-top{top:0}
.idle-overlay.overlay-bottom{bottom:0}
.idle-overlay.overlay-center{top:50%;transform:translateY(-50%)}
.idle-overlay-static{max-width:100%;overflow-wrap:anywhere}
.idle-overlay-marquee{width:100%;overflow:hidden;white-space:nowrap}
.idle-overlay-scroll{display:inline-block;white-space:nowrap;min-width:max-content;padding-left:100%;animation:posnext-idle-ticker linear infinite;will-change:transform}
@keyframes posnext-idle-ticker{from{transform:translateX(0)}to{transform:translateX(-100%)}}
@media(prefers-reduced-motion:reduce){.idle-overlay-scroll{animation:none;padding-left:0;white-space:normal}}

/* 7-inch customer screens: viewport-aware layout, without affecting standard desktop styling.
   A compact layout uses viewport dimensions rather than physical display DPI. */
.customer-display.is-compact{height:100vh;height:100dvh;min-height:0;overflow:hidden}
.is-compact .display-header{height:52px;min-height:52px;flex:0 0 52px;box-sizing:border-box;padding:5px 12px;gap:8px}
.is-compact .company-logo{width:32px;height:32px}
.is-compact .company-name{font-size:17px;line-height:1.1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.is-compact .terminal-meta{font-size:10px;margin-top:1px;gap:8px}
.is-compact .header-status{gap:7px;flex-shrink:0}
.is-compact .display-clock{font-size:10px}
.is-compact .status-pill{font-size:10px;padding:5px 8px;gap:5px}
.is-compact .status-dot{width:6px;height:6px}
.is-compact .display-main{height:calc(100% - 52px);min-height:0;flex:1;overflow:hidden}
/* Override the pre-existing max-width:1050px single-column media rule. */
.is-compact .redesigned-sale{display:grid;grid-template-columns:minmax(0,1fr) minmax(260px,35%);height:100%;min-height:0;overflow:hidden}
.is-compact .cart-main-panel{padding:8px 10px;min-height:0;gap:7px;overflow:hidden}
.is-compact .cart-panel-header{gap:6px}
.is-compact .cart-panel-kicker,.is-compact .card-title{font-size:9px;letter-spacing:.09em}
.is-compact .cart-panel-title{font-size:18px;margin-top:1px}
.is-compact .cart-count-badge{font-size:10px;padding:5px 8px;white-space:nowrap}
.is-compact .cart-history-large{min-height:0;flex:1 1 0;overflow:hidden;border-radius:10px}
.is-compact .cart-history-scroll{flex:1;min-height:0;overflow-y:auto;overflow-x:hidden;overscroll-behavior:contain;padding:5px;gap:4px}
.is-compact .cart-line{gap:6px;padding:5px 6px;border-radius:7px;grid-template-columns:minmax(0,1fr) auto}
.is-compact .cart-line-item{gap:6px;min-width:0}
.is-compact .cart-line-image{width:34px;height:34px;border-radius:6px}
.is-compact .cart-line-copy strong{font-size:11px;line-height:1.2;overflow-wrap:anywhere}
.is-compact .cart-line-meta{font-size:9px}
.is-compact .cart-line-math{min-width:0;grid-template-columns:minmax(55px,1fr) 32px minmax(65px,1fr);gap:4px}
.is-compact .cart-line-math>div{gap:2px}
.is-compact .cart-line-math small{font-size:8px;letter-spacing:0}
.is-compact .cart-line-math strong,.is-compact .cart-math-amount strong{font-size:11px}
.is-compact .cart-math-qty strong{font-size:12px}
.is-compact .totals-card.summary-strip{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:5px;flex:0 0 auto}
.is-compact .summary-tile{padding:6px;gap:3px;border-radius:9px;min-width:0;box-shadow:none}
.is-compact .summary-tile span{font-size:8px;letter-spacing:0;overflow:hidden;text-overflow:ellipsis}
.is-compact .summary-tile strong,.is-compact .summary-tile.grand strong{font-size:clamp(11px,1.5vw,17px);overflow:hidden;text-overflow:ellipsis}
.is-compact .sale-sidebar{min-height:0;overflow:hidden;display:flex;flex-direction:column;gap:6px;border-top:0;border-left:1px solid rgba(255,255,255,.12);padding:7px 8px}
.is-compact .current-item-card{flex:0 1 auto;min-height:0;padding:7px;grid-template-columns:56px minmax(0,1fr);gap:7px;border-radius:10px;align-items:start}
.is-compact .current-item-card.without-image{grid-template-columns:minmax(0,1fr)}
.is-compact .current-item-image-wrap{width:56px;height:56px;border-radius:8px}
.is-compact .current-item-copy h2{font-size:clamp(12px,1.65vw,17px)!important;margin:2px 0 4px;line-height:1.15;overflow-wrap:anywhere}
.is-compact .latest-item-quantity-grid{margin:4px 0;gap:4px}
.is-compact .latest-qty-tile{padding:4px 5px;border-radius:6px;gap:1px}
.is-compact .latest-qty-tile span{font-size:7px;letter-spacing:0}
.is-compact .latest-qty-tile strong{font-size:13px}
.is-compact .current-item-prices,.is-compact .current-item-card.without-image .current-item-prices{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:4px;margin-top:4px}
.is-compact .current-item-prices>div,.is-compact .current-item-prices .final{padding:5px 6px;border-radius:7px;margin:0;gap:2px;display:flex;flex-direction:column;align-items:start}
.is-compact .current-item-prices>div span{font-size:7px;letter-spacing:0}
.is-compact .current-item-prices>div strong,.is-compact .current-item-prices .final strong{font-size:clamp(10px,1.5vw,14px)}
.is-compact .customer-card{padding:6px 8px;border-radius:9px;flex:0 0 auto}
.is-compact .customer-card>div{font-size:10px;gap:6px;padding:2px 0}
.is-compact .customer-card strong{white-space:nowrap;text-align:right;overflow:hidden;text-overflow:ellipsis;max-width:65%}
.is-compact .payment-card-redesigned{flex:0 1 auto;min-height:0;overflow-y:auto;overscroll-behavior:contain;margin-top:auto;padding:7px;border-radius:10px;box-shadow:none;max-height:45%}
.is-compact .payment-card-redesigned>.card-title{margin-bottom:4px}
.is-compact .payment-methods{gap:3px;margin-bottom:5px}
.is-compact .payment-method-row{padding:4px 6px;border-radius:6px;font-size:10px}
.is-compact .payment-method-row strong{font-size:11px}
.is-compact .payment-tiles{gap:5px}
.is-compact .payment-tile{min-height:48px;border-radius:8px;padding:5px;gap:2px;box-shadow:none}
.is-compact .payment-tile span{font-size:8px;letter-spacing:0}
.is-compact .payment-tile strong{font-size:clamp(12px,1.85vw,19px)}
.is-compact .fullscreen-button{width:27px;height:27px;right:4px;bottom:4px;font-size:16px;border-radius:6px;opacity:.6}
.is-compact .idle-screen,.is-compact .message-screen{height:100%;min-height:0}
.is-compact .message-screen{padding:14px;gap:6px;overflow:auto}
.is-compact .message-icon{width:44px;height:44px;font-size:26px}
.is-compact .message-screen h1{font-size:clamp(30px,6vh,48px)}
.is-compact .message-screen>p{font-size:clamp(13px,3vh,19px)}
.is-compact .message-screen .payment-card{width:min(560px,92vw);max-height:44vh;overflow:auto}
.is-compact .welcome-panel h1{font-size:clamp(28px,7vw,70px)}
/* Extra-dense 800x480 portrait-safe landscape layout. */
@media(max-width:880px){
 .is-compact .redesigned-sale{grid-template-columns:minmax(0,1fr) minmax(258px,36%)}
 .is-compact .cart-main-panel{padding:6px;gap:5px}
 .is-compact .cart-line{padding:4px}
 .is-compact .cart-line-image{width:27px;height:27px}
 .is-compact .cart-line-math{grid-template-columns:minmax(45px,1fr) 23px minmax(56px,1fr);gap:2px}
 .is-compact .cart-line-math strong,.is-compact .cart-math-amount strong{font-size:10px}
 .is-compact .summary-tile{padding:5px 4px}
 .is-compact .sale-sidebar{padding:5px;gap:4px}
 .is-compact .current-item-card{grid-template-columns:42px minmax(0,1fr);padding:5px;gap:5px}
 .is-compact .current-item-image-wrap{width:42px;height:42px}
 .is-compact .latest-qty-tile{padding:3px}
 .is-compact .customer-card{padding:5px 6px}
 .is-compact .payment-card-redesigned{padding:5px}
}
@media(max-height:530px){
 .is-compact .display-header{height:43px;min-height:43px;flex-basis:43px;padding:3px 9px}
 .is-compact .company-logo{width:27px;height:27px}
 .is-compact .company-name{font-size:15px}
 .is-compact .display-main{height:calc(100% - 43px)}
 .is-compact .current-item-image-wrap{width:36px;height:36px}
 .is-compact .current-item-card{grid-template-columns:36px minmax(0,1fr)}
 .is-compact .current-item-card.without-image{grid-template-columns:minmax(0,1fr)}
 .is-compact .latest-qty-tile strong{font-size:12px}
 .is-compact .payment-tile{min-height:40px}
}

</style>
