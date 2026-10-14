<template>
  <div
    v-if="modelValue"
    class="fixed inset-0 z-[320] bg-black/50 flex items-center justify-center p-4"
    @click.self="close"
  >
    <div class="w-full max-w-2xl bg-white rounded-xl shadow-2xl flex flex-col max-h-[85vh]" dir="rtl">
      <!-- Header -->
      <div class="flex items-center justify-between px-5 py-4 border-b border-gray-200">
        <div>
          <h2 class="font-bold text-lg text-gray-900">{{ __('مشتريات العميل') }}</h2>
          <p class="text-xs text-gray-500 mt-0.5">{{ __('الأصناف التي طلبها العميل والكميات وتواريخ الطلب') }}</p>
        </div>
        <button class="text-gray-500 text-2xl leading-none" @click="close">×</button>
      </div>

      <!-- No customer selected -->
      <div v-if="!customerName" class="p-6 text-sm text-amber-800 bg-amber-50 m-4 rounded-lg border border-amber-200">
        {{ __('اختر العميل أولًا من شاشة البيع ثم أعد المحاولة.') }}
      </div>

      <template v-else>
        <div class="px-5 py-3 bg-gray-50 border-b border-gray-200">
          <span class="text-xs text-gray-500">{{ __('العميل') }}:</span>
          <span class="font-semibold text-gray-900 ms-1">{{ customerName }}</span>
        </div>

        <!-- Body -->
        <div class="flex-1 overflow-y-auto p-4">
          <div v-if="loading" class="text-center text-gray-500 py-10">{{ __('جارٍ التحميل…') }}</div>

          <div v-else-if="rows.length === 0" class="text-center text-gray-500 py-10">
            {{ __('لا توجد مشتريات سابقة لهذا العميل.') }}
          </div>

          <table v-else class="w-full text-sm">
            <thead class="text-gray-500 text-xs border-b border-gray-200">
              <tr>
                <th class="text-start py-2 font-medium">{{ __('الصنف') }}</th>
                <th class="text-center py-2 font-medium w-24">{{ __('الكمية') }}</th>
                <th class="text-start py-2 font-medium w-32">{{ __('تاريخ الطلب') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, i) in rows" :key="i" class="border-b border-gray-100">
                <td class="py-2">
                  <div class="font-medium text-gray-900">{{ row.item_name || row.item_code }}</div>
                  <div class="text-[11px] text-gray-400">{{ row.item_code }}</div>
                </td>
                <td class="py-2 text-center font-semibold text-gray-800">
                  {{ formatQty(row.qty) }} <span class="text-[11px] text-gray-400">{{ row.uom }}</span>
                </td>
                <td class="py-2 text-gray-600">{{ formatDate(row.posting_date) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>

      <!-- Footer -->
      <div class="px-5 py-3 border-t border-gray-200 flex justify-end">
        <button
          class="px-5 py-2 rounded-lg font-semibold text-gray-700 bg-gray-100 hover:bg-gray-200 transition-colors"
          @click="close"
        >
          {{ __('إغلاق') }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import { call } from "frappe-ui"
import { useToast } from "@/composables/useToast"

const props = defineProps({
  modelValue: Boolean,
  posProfile: String,
  customer: [String, Object],
})
const emit = defineEmits(["update:modelValue"])
const { showError } = useToast()

const rows = ref([])
const loading = ref(false)

const customerName = computed(() => {
  const c = props.customer
  if (!c) return ""
  return typeof c === "string" ? c : (c.customer_name || c.name || "")
})
const customerId = computed(() => {
  const c = props.customer
  if (!c) return ""
  return typeof c === "string" ? c : (c.name || "")
})

function close() {
  emit("update:modelValue", false)
}

function formatQty(q) {
  const n = Number(q || 0)
  return Number.isInteger(n) ? n : n.toFixed(2)
}
function formatDate(d) {
  if (!d) return ""
  try {
    return new Date(d).toLocaleDateString("ar-SA")
  } catch (e) {
    return d
  }
}

async function loadOrders() {
  if (!customerId.value) return
  loading.value = true
  rows.value = []
  try {
    const res = await call("pos_next.api.customers.get_customer_ordered_items", {
      customer: customerId.value,
      pos_profile: props.posProfile,
    })
    rows.value = (res && (res.message ?? res)) || []
  } catch (e) {
    rows.value = []
    showError(e?.message || __("تعذّر جلب مشتريات العميل"))
  } finally {
    loading.value = false
  }
}

watch(() => props.modelValue, (v) => { if (v) loadOrders() })
</script>
