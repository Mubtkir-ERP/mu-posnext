<template>
	<Dialog v-model="show" :options="{ title: __('Customer Branch QR Code'), size: 'sm' }">
		<template #body-content>
			<div class="flex flex-col items-center text-center p-2">
				<!-- Customer & Branch info -->
				<h3 class="text-base font-bold text-gray-900 mb-1">
					{{ customerName }}
				</h3>
				<span class="inline-flex items-center gap-1 bg-blue-50 text-blue-700 text-xs font-semibold px-2.5 py-0.5 rounded-full border border-blue-200 mb-3">
					🏢 {{ branchTitle }}
				</span>

				<!-- QR Image Container -->
				<div class="bg-gray-50 border-2 border-dashed border-gray-300 rounded-xl p-3 mb-3 flex items-center justify-center">
					<img
						v-if="qrImage"
						:src="qrImage"
						alt="Branch QR"
						class="w-48 h-48 rounded shadow-sm"
					/>
					<div v-else class="w-48 h-48 flex items-center justify-center text-gray-400 text-xs">
						{{ __("Generating QR...") }}
					</div>
				</div>

				<!-- Details -->
				<div v-if="addressLine || city" class="text-xs text-gray-600 mb-1">
					📍 {{ addressLine }} {{ city ? `(${city})` : '' }}
				</div>
				<div v-if="phone" class="text-xs text-gray-600 mb-2">
					📞 {{ phone }}
				</div>

				<p class="text-[11px] text-gray-400 mb-4 border-t border-gray-100 pt-2 w-full">
					{{ __("Scan this QR code with a barcode reader or camera to select this branch in POS.") }}
				</p>

				<!-- Print Button -->
				<div class="flex gap-2 w-full">
					<button
						type="button"
						@click="printCard"
						class="flex-1 flex items-center justify-center gap-1.5 py-2 px-4 bg-blue-600 hover:bg-blue-700 active:bg-blue-800 text-white text-xs font-semibold rounded-lg shadow-sm transition-colors"
					>
						<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z" />
						</svg>
						<span>{{ __("Print Card / Sticker") }}</span>
					</button>
					<button
						type="button"
						@click="show = false"
						class="py-2 px-4 bg-gray-100 hover:bg-gray-200 text-gray-700 text-xs font-semibold rounded-lg transition-colors"
					>
						{{ __("Close") }}
					</button>
				</div>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { computed } from "vue";
import { Dialog } from "frappe-ui";
import { call } from "@/utils/apiWrapper";

const props = defineProps({
	modelValue: Boolean,
	customer: [Object, String],
	branch: Object,
});

const emit = defineEmits(["update:modelValue"]);

const show = computed({
	get: () => props.modelValue,
	set: (val) => emit("update:modelValue", val),
});

const customerName = computed(() => {
	if (!props.customer) return "";
	return typeof props.customer === "object"
		? props.customer.customer_name || props.customer.name
		: props.customer;
});

const customerId = computed(() => {
	if (!props.customer) return "";
	return typeof props.customer === "object" ? props.customer.name : props.customer;
});

const branchTitle = computed(() => props.branch?.branch_title || props.branch?.address_name || "");
const addressLine = computed(() => props.branch?.address_line1 || "");
const city = computed(() => props.branch?.city || "");
const phone = computed(() => props.branch?.phone || "");
const qrImage = computed(() => props.branch?.qr_image || "");

async function printCard() {
	if (!customerId.value || !props.branch?.address_name) return;
	try {
		const html = await call("pos_next.operations.customer_branches.get_branch_qr_card_html", {
			customer: customerId.value,
			address_name: props.branch.address_name,
		});
		const printWin = window.open("", "_blank");
		if (printWin) {
			printWin.document.open();
			printWin.document.write(html);
			printWin.document.close();
		}
	} catch (err) {
		console.error("Print card error:", err);
	}
}
</script>
