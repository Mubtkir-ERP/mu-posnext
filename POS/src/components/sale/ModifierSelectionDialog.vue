<template>
	<div
		v-if="modelValue"
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
		@click.self="close"
	>
		<div class="w-full max-w-lg rounded-2xl bg-white shadow-xl overflow-hidden flex flex-col max-h-[85vh]">
			<!-- Header -->
			<div class="flex items-center justify-between border-b px-5 py-3.5 bg-slate-50">
				<div>
					<h3 class="text-base font-bold text-slate-900">{{ item?.item_name || item?.item_code }}</h3>
					<p class="text-xs text-slate-500">{{ __("Select Modifiers & Add-ons") }}</p>
				</div>
				<button
					type="button"
					class="rounded-lg p-1.5 text-slate-400 hover:bg-slate-200 hover:text-slate-700"
					@click="close"
				>
					✕
				</button>
			</div>

			<!-- Body -->
			<div class="flex-1 overflow-y-auto p-5 space-y-4">
				<div v-if="loading" class="py-8 text-center text-sm text-slate-500">
					{{ __("Loading modifiers...") }}
				</div>

				<template v-else>
					<div v-for="group in groups" :key="group.name" class="space-y-2">
						<div class="flex items-center justify-between">
							<span class="text-sm font-bold text-slate-800">{{ group.group_name }}</span>
							<span
								v-if="group.is_required"
								class="rounded-full bg-red-50 px-2 py-0.5 text-[11px] font-semibold text-red-600"
							>
								{{ __("Required") }}
							</span>
						</div>

						<div class="grid grid-cols-2 gap-2">
							<button
								v-for="opt in group.options"
								:key="opt.name"
								type="button"
								class="flex items-center justify-between rounded-xl border px-3 py-2 text-xs font-medium transition"
								:class="isSelected(group, opt)
									? 'border-blue-600 bg-blue-50 text-blue-800'
									: 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50'"
								@click="toggleOption(group, opt)"
							>
								<span class="truncate">{{ opt.label }}</span>
								<span
									v-if="opt.option_type === 'Paid Item' && opt.price > 0"
									class="ms-2 shrink-0 font-bold text-emerald-700"
								>
									+{{ opt.price.toFixed(2) }}
								</span>
								<span v-else class="ms-2 shrink-0 text-[11px] text-slate-400">
									{{ __("Free") }}
								</span>
							</button>
						</div>
					</div>

					<div>
						<label class="block text-xs font-semibold text-slate-600 mb-1">
							{{ __("Kitchen Note (Optional)") }}
						</label>
						<input
							v-model="itemNote"
							type="text"
							class="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
							:placeholder="__('e.g. Extra hot, no onions...')"
						/>
					</div>
				</template>
			</div>

			<!-- Footer -->
			<div class="flex items-center justify-between border-t bg-slate-50 px-5 py-3">
				<div class="text-xs font-semibold text-slate-600">
					{{ __("Extra") }}: <span class="text-emerald-700 font-bold">+{{ extraTotal.toFixed(2) }}</span>
				</div>
				<div class="flex items-center gap-2">
					<button
						type="button"
						class="rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-100"
						@click="close"
					>
						{{ __("Cancel") }}
					</button>
					<button
						type="button"
						class="rounded-xl bg-blue-600 px-5 py-2 text-sm font-bold text-white hover:bg-blue-700 disabled:opacity-50"
						:disabled="loading"
						@click="confirm"
					>
						{{ __("Add to Cart") }}
					</button>
				</div>
			</div>
		</div>
	</div>
</template>

<script setup>
import { ref, watch, computed } from "vue";
import { call } from "@/utils/apiWrapper";
import { useToast } from "@/composables/useToast";

const { showWarning } = useToast();

const props = defineProps({
	modelValue: { type: Boolean, default: false },
	item: { type: Object, default: null },
	priceList: { type: String, default: "" },
});

const emit = defineEmits(["update:modelValue", "confirm"]);

const loading = ref(false);
const groups = ref([]);
const selectedByGroup = ref({});
const itemNote = ref("");

watch(
	() => [props.modelValue, props.item?.item_code],
	async ([open, itemCode]) => {
		if (!open || !itemCode) return;
		loading.value = true;
		itemNote.value = "";
		selectedByGroup.value = {};
		try {
			const res = await call("pos_next.api.modifiers.get_item_modifiers", {
				item_code: itemCode,
				price_list: props.priceList || null,
			});
			groups.value = Array.isArray(res) ? res : [];
			const initSel = {};
			for (const g of groups.value) {
				initSel[g.name] = g.options.filter((o) => o.is_default).map((o) => o.name);
				if (g.selection_type === "Single" && initSel[g.name].length > 1) {
					initSel[g.name] = [initSel[g.name][0]];
				}
			}
			selectedByGroup.value = initSel;
		} catch (e) {
			groups.value = [];
		} finally {
			loading.value = false;
		}
	},
	{ immediate: true }
);

function isSelected(group, opt) {
	return (selectedByGroup.value[group.name] || []).includes(opt.name);
}

function toggleOption(group, opt) {
	const current = [...(selectedByGroup.value[group.name] || [])];
	if (group.selection_type === "Single") {
		selectedByGroup.value[group.name] = current.includes(opt.name) ? [] : [opt.name];
	} else {
		const idx = current.indexOf(opt.name);
		if (idx >= 0) current.splice(idx, 1);
		else current.push(opt.name);
		selectedByGroup.value[group.name] = current;
	}
}

const extraTotal = computed(() => {
	let sum = 0;
	for (const g of groups.value) {
		const sel = selectedByGroup.value[g.name] || [];
		for (const o of g.options) {
			if (sel.includes(o.name) && o.option_type === "Paid Item") {
				sum += Number(o.price || 0);
			}
		}
	}
	return sum;
});

function close() {
	emit("update:modelValue", false);
}

function confirm() {
	for (const g of groups.value) {
		if (g.is_required && !(selectedByGroup.value[g.name] || []).length) {
			showWarning(__("Please select an option for {0}", [g.group_name]));
			return;
		}
	}

	const labels = [];
	const paidModifiers = [];
	for (const g of groups.value) {
		const sel = selectedByGroup.value[g.name] || [];
		for (const o of g.options) {
			if (!sel.includes(o.name)) continue;
			labels.push(o.option_type === "Paid Item" && o.price > 0 ? `${o.label} (+${o.price.toFixed(2)})` : o.label);
			if (o.option_type === "Paid Item" && o.item_code) {
				paidModifiers.push(o);
			}
		}
	}

	emit("confirm", {
		item: props.item,
		modifierSummary: labels.join("، "),
		itemNote: itemNote.value.trim(),
		paidModifiers,
	});
	close();
}
</script>
