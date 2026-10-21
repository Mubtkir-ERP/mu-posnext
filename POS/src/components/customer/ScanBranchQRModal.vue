<template>
	<Dialog v-model="show" :options="{ title: __('Scan Customer Branch QR'), size: 'sm' }">
		<template #body-content>
			<div class="flex flex-col gap-4 p-1">
				<div class="text-center text-xs text-gray-500">
					{{ __("Scan the customer's branch QR card with a 2D barcode scanner, or paste the code below:") }}
				</div>

				<div class="relative">
					<input
						ref="inputRef"
						v-model="qrInput"
						type="text"
						:placeholder="__('Scan or paste QR code here (MUBTKIR_BRANCH::...)')"
						class="w-full text-xs border border-gray-300 rounded-xl px-3 py-2.5 focus:ring-2 focus:ring-blue-500 focus:outline-none"
						@keydown.enter.prevent="handleSubmit"
						@input="handleInput"
						autofocus
					/>
				</div>

				<div v-if="errorMsg" class="text-xs text-red-600 bg-red-50 p-2 rounded-lg text-center">
					{{ errorMsg }}
				</div>

				<div class="flex gap-2 justify-end mt-2">
					<button
						type="button"
						@click="handleSubmit"
						:disabled="loading || !qrInput.trim()"
						class="flex-1 py-2 px-4 bg-blue-600 hover:bg-blue-700 active:bg-blue-800 disabled:opacity-50 text-white text-xs font-semibold rounded-lg shadow-sm transition-colors flex items-center justify-center gap-1.5"
					>
						<span v-if="loading" class="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
						<span>{{ __("Confirm Selection") }}</span>
					</button>
					<button
						type="button"
						@click="show = false"
						class="py-2 px-4 bg-gray-100 hover:bg-gray-200 text-gray-700 text-xs font-semibold rounded-lg transition-colors"
					>
						{{ __("Cancel") }}
					</button>
				</div>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { computed, ref, watch, nextTick } from "vue";
import { Dialog } from "frappe-ui";
import { call } from "@/utils/apiWrapper";

const props = defineProps({
	modelValue: Boolean,
});

const emit = defineEmits(["update:modelValue", "branch-resolved"]);

const show = computed({
	get: () => props.modelValue,
	set: (val) => emit("update:modelValue", val),
});

const qrInput = ref("");
const loading = ref(false);
const errorMsg = ref("");
const inputRef = ref(null);

watch(show, (newVal) => {
	if (newVal) {
		qrInput.value = "";
		errorMsg.value = "";
		nextTick(() => {
			inputRef.value?.focus();
		});
	}
});

function handleInput() {
	errorMsg.value = "";
	const val = qrInput.value.trim();
	// If barcode scanner inputs with newline or instantly has MUBTKIR_BRANCH::, auto-submit
	if (val.startsWith("MUBTKIR_BRANCH::") && val.split("::").length >= 3) {
		handleSubmit();
	}
}

async function handleSubmit() {
	const text = qrInput.value.trim();
	if (!text) return;

	loading.value = true;
	errorMsg.value = "";

	try {
		const res = await call("pos_next.operations.customer_branches.resolve_customer_branch", {
			qr_code_content: text,
		});

		if (res && res.status === "success" && res.customer) {
			emit("branch-resolved", res);
			show.value = false;
		} else {
			errorMsg.value = __("Could not resolve branch from QR code.");
		}
	} catch (err) {
		errorMsg.value = err?.message || __("Invalid or unknown Branch QR code.");
	} finally {
		loading.value = false;
	}
}
</script>
