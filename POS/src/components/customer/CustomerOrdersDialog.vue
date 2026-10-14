<template>
  <div
    v-if="modelValue"
    class="fixed inset-0 z-[320] bg-black/50 flex items-center justify-center p-4"
    @click.self="close"
  >
    <div class="w-full max-w-2xl bg-white rounded-xl shadow-2xl flex flex-col max-h-[88vh]" dir="rtl">
      <!-- Header -->
      <div class="flex items-center justify-between px-5 py-4 border-b border-gray-200">
        <div>
          <h2 class="font-bold text-lg text-gray-900">{{ __('مشتريات العميل') }}</h2>
          <p class="text-xs text-gray-500 mt-0.5">{{ __('ابحث عن العميل بالاسم أو رقم الجوال لعرض مشترياته') }}</p>
        </div>
        <button class="text-gray-500 text-2xl leading-none" @click="close">×</button>
      </div>

      <!-- Search box -->
      <div class="px-5 pt-4">
        <div class="relative">
          <input
            ref="searchInput"
            v-model="query"
            type="text"
            :placeholder="__('اكتب اسم العميل أو رقم الجوال…')"
            class="w-full border-2 border-blue-400 rounded-xl py-3 ps-4 pe-10 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
            @input="onSearchInput"
          />
          <span class="absolute inset-y-0 end-3 flex items-center text-gray-400">🔍</span>
        </div>
      </div>

      <!-- Body -->
      <div class="flex-1 overflow-y-auto p-5">
        <!-- Customer results (before a customer is picked) -->
        <div v-if="!selectedCustomer">
          <div v-if="searching" class="text-center text-gray-500 py-8">{{ __('جارٍ البحث…') }}</div>
          <div v-else-if="query && customers.length === 0" class="text-center text-gray-500 py-8">
            {{ __('لا يوجد عميل مطابق.') }}
          </div>
          <div v-else-if="!query" class="text-center text-gray-400 py-10">
            {{ __('ابدأ بالكتابة للبحث عن عميل.') }}
          </div>
          <ul v-else class="flex flex-col gap-1">
            <li
              v-for="c in customers"
              :key="c.name"
              class="flex items-center justify-between px-3 py-2.5 rounded-lg hover:bg-blue-50 cursor-pointer border border-gray-100"
              @click="pickCustomer(c)"
            >
              <div>
                <div class="font-semibold text-gray-900 text-sm">{{ c.customer_name || c.name }}</div>
                <div class="text-xs text-gray-400">{{ c.mobile_no || c.name }}</div>
              </div>
              <span class="text-blue-600 text-xs">{{ __('عرض') }} ‹</span>
            </li>
          </ul>
        </div>

        <!-- Orders of the selected customer -->
        <div v-else>
          <button class="text-blue-600 text-xs mb-3 flex items-center gap-1" @click="backToSearch">
            › {{ __('رجوع للبحث') }}
          </button>
          <div class="px-1 pb-3 mb-2 border-b border-gray-200">
            <span class="text-xs text-gray-500">{{ __('العميل') }}:</span>
            <span class="font-semibold text-gray-900 ms-1">{{ selectedCustomer.customer_name || selectedCustomer.name }}</span>
          </div>

          <div v-if="loading" class="text-center text-gray-500 py-8">{{ __('جارٍ التحميل…') }}</div>
          <div v-else-if="rows.length === 0" class="text-center text-gray-500 py-8">
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
      </div>

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
import { ref, watch, nextTick } from "vue"
import { call } from "frappe-ui"
import { useToast } from "@/composables/useToast"

const props = defineProps({
  modelValue: Boolean,
  posProfile: String,
})
const emit = defineEmits(["update:modelValue"])
const { showError } = useToast()

const query = ref("")
const customers = ref([])
const searching = ref(false)
const selectedCustomer = ref(null)
const rows = ref([])
const loading = ref(false)
const searchInput = ref(null)
let searchTimer = null

function close() {
  emit("update:modelValue", false)
}

function formatQty(q) {
  const n = Number(q || 0)
  return Number.isInteger(n) ? n : n.toFixed(2)
}
function formatDate(d) {
  if (!d) return ""
  try { return new Date(d).toLocaleDateString("ar-SA") } catch (e) { return d }
}

function onSearchInput() {
  clearTimeout(searchTimer)
  const q = query.value.trim()
  if (!q) { customers.value = []; return }
  searchTimer = setTimeout(() => searchCustomers(q), 300)
}

async function searchCustomers(q) {
  searching.value = true
  try {
    const res = await call("pos_next.api.customers.get_customers", {
      search_term: q,
      limit: 20,
    })
    customers.value = (res && (res.message ?? res)) || []
  } catch (e) {
    customers.value = []
    showError(e?.message || __("تعذّر البحث عن العملاء"))
  } finally {
    searching.value = false
  }
}

async function pickCustomer(c) {
  selectedCustomer.value = c
  loading.value = true
  rows.value = []
  try {
    const res = await call("pos_next.api.customers.get_customer_ordered_items", {
      customer: c.name,
    })
    rows.value = (res && (res.message ?? res)) || []
  } catch (e) {
    rows.value = []
    showError(e?.message || __("تعذّر جلب مشتريات العميل"))
  } finally {
    loading.value = false
  }
}

function backToSearch() {
  selectedCustomer.value = null
  rows.value = []
  nextTick(() => searchInput.value?.focus())
}

watch(() => props.modelValue, (v) => {
  if (v) {
    query.value = ""
    customers.value = []
    selectedCustomer.value = null
    rows.value = []
    nextTick(() => searchInput.value?.focus())
  }
})
</script>
