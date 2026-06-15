<template>
	<Teleport to="body">
		<Transition name="modal-fade">
			<div
				v-if="show"
				class="fixed inset-0 z-[9999] flex items-center justify-center p-4"
				style="background: rgba(0,0,0,0.55); backdrop-filter: blur(3px)"
				@click.self="close"
			>
				<div
					class="bg-white rounded-2xl shadow-2xl w-full max-w-md flex flex-col"
					style="max-height: 90vh"
					@click.stop
				>
					<!-- Header -->
					<div class="flex items-center justify-between px-6 py-5 border-b border-gray-100">
						<div class="flex items-center gap-3">
							<!-- Cash icon -->
							<div class="w-10 h-10 rounded-xl bg-amber-50 flex items-center justify-center flex-shrink-0">
								<svg class="w-5 h-5 text-amber-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
										d="M17 9V7a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2m2 4h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2zm7-5a2 2 0 11-4 0 2 2 0 014 0z"/>
								</svg>
							</div>
							<div>
								<h2 class="text-base font-bold text-gray-900">{{ __("Cash Disbursement") }}</h2>
								<p class="text-xs text-gray-400 mt-0.5">{{ __("صرف نقدي من الدرج") }}</p>
							</div>
						</div>
						<button
							class="w-8 h-8 rounded-lg hover:bg-gray-100 flex items-center justify-center text-gray-400 hover:text-gray-600 transition-colors"
							@click="close"
						>
							<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
							</svg>
						</button>
					</div>

					<!-- Form Body -->
					<div class="flex-1 overflow-y-auto p-6 flex flex-col gap-5">

						<!-- Amount -->
						<div class="flex flex-col gap-1.5">
							<label class="text-sm font-semibold text-gray-700">
								{{ __("Amount") }}
								<span class="text-red-500 ms-0.5">*</span>
							</label>
							<div class="relative">
								<span class="absolute inset-y-0 start-3 flex items-center text-gray-400 text-sm font-medium pointer-events-none select-none">
									{{ currency }}
								</span>
								<input
									ref="amountInput"
									v-model.number="form.amount"
									type="number"
									min="0.01"
									step="0.01"
									:placeholder="__('0.00')"
									class="w-full border border-gray-200 rounded-xl py-3 text-end text-lg font-bold text-gray-800 focus:outline-none focus:ring-2 focus:ring-amber-300 focus:border-amber-400 bg-gray-50 hover:bg-white transition-colors"
									:class="{ 'border-red-400 bg-red-50': errors.amount }"
									style="padding-inline-start: 2.5rem; padding-inline-end: 1rem"
									@keyup.enter="submitDisbursement"
									@input="errors.amount = ''"
								/>
							</div>
							<p v-if="errors.amount" class="text-xs text-red-500 flex items-center gap-1">
								<svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clip-rule="evenodd"/></svg>
								{{ errors.amount }}
							</p>
						</div>

						<!-- Reason -->
						<div class="flex flex-col gap-1.5">
							<label class="text-sm font-semibold text-gray-700">
								{{ __("Reason / Description") }}
								<span class="text-red-500 ms-0.5">*</span>
							</label>
							<textarea
								v-model="form.reason"
								rows="3"
								:placeholder="__('e.g. Employee advance – John, maintenance fee ...')"
								class="w-full border border-gray-200 rounded-xl py-3 px-4 text-sm text-gray-800 focus:outline-none focus:ring-2 focus:ring-amber-300 focus:border-amber-400 bg-gray-50 hover:bg-white transition-colors resize-none"
								:class="{ 'border-red-400 bg-red-50': errors.reason }"
								@input="errors.reason = ''"
							/>
							<p v-if="errors.reason" class="text-xs text-red-500 flex items-center gap-1">
								<svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clip-rule="evenodd"/></svg>
								{{ errors.reason }}
							</p>
						</div>

						<!-- Disbursements History -->
						<div v-if="history.length > 0" class="flex flex-col gap-2">
							<div class="flex items-center justify-between">
								<p class="text-xs font-semibold text-gray-500 uppercase tracking-wide">
									{{ __("Today's Disbursements") }}
								</p>
								<p class="text-xs font-bold text-amber-600">
									{{ __("Total:") }} {{ formatCurrency(totalDisbursed) }}
								</p>
							</div>
							<div class="flex flex-col gap-1.5 max-h-36 overflow-y-auto">
								<div
									v-for="item in history"
									:key="item.name"
									class="flex items-center gap-3 bg-amber-50 border border-amber-100 rounded-xl px-3 py-2"
								>
									<div class="flex-1 min-w-0">
										<p class="text-xs font-semibold text-gray-800 truncate">{{ item.reason }}</p>
										<p class="text-xs text-gray-400">{{ item.name }}</p>
									</div>
									<p class="text-sm font-bold text-amber-700 flex-shrink-0">
										{{ formatCurrency(item.amount) }}
									</p>
									<button
										v-if="!cancellingId"
										class="w-6 h-6 rounded-lg hover:bg-red-100 flex items-center justify-center text-gray-300 hover:text-red-500 transition-colors flex-shrink-0"
										:title="__('Cancel disbursement')"
										@click="cancelDisbursement(item)"
									>
										<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
											<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18L18 6M6 6l12 12"/>
										</svg>
									</button>
									<div v-else-if="cancellingId === item.name" class="w-4 h-4 border-2 border-red-400 border-t-transparent rounded-full animate-spin flex-shrink-0"/>
								</div>
							</div>
						</div>
					</div>

					<!-- Footer -->
					<div class="px-6 py-4 border-t border-gray-100 flex gap-3">
						<button
							class="flex-1 py-3 rounded-xl border border-gray-200 text-sm font-semibold text-gray-600 hover:bg-gray-50 transition-colors"
							:disabled="submitting"
							@click="close"
						>
							{{ __("Cancel") }}
						</button>
						<button
							class="flex-1 py-3 rounded-xl text-sm font-bold text-white transition-all flex items-center justify-center gap-2 shadow-sm"
							:class="submitting ? 'bg-amber-300 cursor-not-allowed' : 'bg-amber-500 hover:bg-amber-600 active:scale-95'"
							:disabled="submitting"
							@click="submitDisbursement"
						>
							<svg v-if="!submitting" class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
									d="M12 6v6m0 0v6m0-6h6m-6 0H6"/>
							</svg>
							<svg v-else class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
								<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
								<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
							</svg>
							{{ submitting ? __("Processing...") : __("Confirm Disbursement") }}
						</button>
					</div>
				</div>
			</div>
		</Transition>
	</Teleport>
</template>

<script setup>
import { ref, reactive, computed, watch, nextTick } from "vue"
import { call } from "@/utils/apiWrapper"
import { logger } from "@/utils/logger"

const log = logger.create("CashDisbursement")

// ─── Props & Emits ───────────────────────────────────────────────────────────
const props = defineProps({
	show: { type: Boolean, default: false },
	shiftName: { type: String, required: true },
	posProfile: { type: String, required: true },
	company: { type: String, required: true },
	currency: { type: String, default: "SAR" },
})

const emit = defineEmits(["update:show", "disbursed"])

// ─── State ───────────────────────────────────────────────────────────────────
const amountInput = ref(null)
const submitting = ref(false)
const cancellingId = ref(null)
const disbursementAccounts = ref([])
const history = ref([])

const form = reactive({
	amount: null,
	reason: "",
})

const errors = reactive({
	amount: "",
	reason: "",
})

// ─── Computed ────────────────────────────────────────────────────────────────
const totalDisbursed = computed(() =>
	history.value.reduce((sum, d) => sum + (d.amount || 0), 0)
)

// ─── Helpers ─────────────────────────────────────────────────────────────────
function formatCurrency(amount) {
	return `${Number(amount || 0).toFixed(2)} ${props.currency}`
}

function resetForm() {
	form.amount = null
	form.reason = ""
	errors.amount = ""
	errors.reason = ""
}

function validate() {
	let valid = true
	errors.amount = ""
	errors.reason = ""

	if (!form.amount || Number(form.amount) <= 0) {
		errors.amount = __("Please enter a valid amount greater than zero.")
		valid = false
	}
	if (!form.reason || !form.reason.trim()) {
		errors.reason = __("Please provide a reason for the disbursement.")
		valid = false
	}
	return valid
}

// ─── API calls ───────────────────────────────────────────────────────────────

async function loadHistory() {
	if (!props.shiftName) return
	try {
		const data = await call(
			"pos_next.api.cash_disbursement.get_shift_disbursements",
			{ shift_name: props.shiftName }
		)
		history.value = data?.message || data || []
	} catch (err) {
		log.warn("Could not load disbursement history:", err?.message)
	}
}

async function submitDisbursement() {
	if (!validate()) return

	submitting.value = true
	try {
		const result = await call(
			"pos_next.api.cash_disbursement.create_cash_disbursement",
			{
				shift_name: props.shiftName,
				amount: form.amount,
				reason: form.reason.trim(),
				pos_profile: props.posProfile,
				company: props.company,
			}
		)
		const data = result?.message || result
		log.info("Disbursement created:", data?.name)

		// Add to history list
		history.value.push({
			name: data.name,
			amount: data.amount,
			reason: data.reason,
			posting_date: data.posting_date,
		})

		// Notify parent
		emit("disbursed", { amount: data.amount, reason: data.reason, name: data.name })

		// Reset form for next entry (don't close — user may want to add more)
		resetForm()

		// Show success toast using frappe
		window.frappe?.show_alert?.({
			message: `${__("Cash disbursement recorded")}: ${formatCurrency(data.amount)}`,
			indicator: "green",
		})

		// Re-focus amount input
		await nextTick()
		amountInput.value?.focus()

	} catch (err) {
		log.error("Disbursement failed:", err?.message)
		window.frappe?.msgprint?.({
			title: __("Error"),
			message: err?.messages?.[0] || err?.message || __("Failed to record disbursement."),
			indicator: "red",
		})
	} finally {
		submitting.value = false
	}
}

async function cancelDisbursement(item) {
	if (!confirm(__("Cancel this disbursement of {0}?", [formatCurrency(item.amount)]))) return

	cancellingId.value = item.name
	try {
		await call(
			"pos_next.api.cash_disbursement.cancel_disbursement",
			{ journal_entry_name: item.name }
		)
		history.value = history.value.filter(d => d.name !== item.name)
		emit("disbursed", { cancelled: true, name: item.name, amount: -item.amount })
		window.frappe?.show_alert?.({
			message: __("Disbursement cancelled"),
			indicator: "orange",
		})
	} catch (err) {
		log.error("Cancel failed:", err?.message)
		window.frappe?.msgprint?.({
			title: __("Error"),
			message: err?.messages?.[0] || err?.message || __("Failed to cancel disbursement."),
			indicator: "red",
		})
	} finally {
		cancellingId.value = null
	}
}

function close() {
	if (submitting.value) return
	emit("update:show", false)
}

// ─── Watchers ────────────────────────────────────────────────────────────────
watch(
	() => props.show,
	async (visible) => {
		if (visible) {
			resetForm()
			await Promise.all([loadHistory()])
			await nextTick()
			amountInput.value?.focus()
		}
	}
)
</script>

<style scoped>
.modal-fade-enter-active,
.modal-fade-leave-active {
	transition: opacity 0.2s ease;
}
.modal-fade-enter-active .bg-white,
.modal-fade-leave-active .bg-white {
	transition: transform 0.2s ease, opacity 0.2s ease;
}
.modal-fade-enter-from,
.modal-fade-leave-to {
	opacity: 0;
}
.modal-fade-enter-from .bg-white {
	transform: scale(0.95) translateY(8px);
	opacity: 0;
}
</style>
