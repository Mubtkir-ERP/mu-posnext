<template>
  <div
    v-if="modelValue"
    class="fixed inset-0 z-[320] bg-black/50 flex items-center justify-center p-4"
    @click.self="close"
  >
    <div class="w-full max-w-md bg-white rounded-xl shadow-2xl p-5 space-y-4">
      <div class="flex items-center justify-between">
        <h2 class="font-bold text-lg text-gray-900">{{ __('Redeem Voucher') }}</h2>
        <button class="text-gray-500 text-2xl leading-none" @click="close">×</button>
      </div>

      <!-- No customer selected -->
      <div v-if="!customerName" class="p-4 rounded-lg bg-amber-50 border border-amber-200 text-sm text-amber-800">
        {{ __('Select a customer on the sale screen first, then try again.') }}
      </div>

      <template v-else>
        <div class="p-3 rounded-lg bg-gray-50 border border-gray-200">
          <div class="text-xs text-gray-500">{{ __('Customer') }}</div>
          <div class="font-semibold text-gray-900">{{ customerName }}</div>
        </div>

        <!-- Branch / Address selection for customer -->
        <div v-if="branches.length > 1" class="p-3 rounded-lg bg-blue-50/60 border border-blue-200">
          <div class="text-xs font-semibold text-blue-800 mb-1 flex items-center justify-between">
            <span>{{ __('Branch / Address') }}</span>
            <span class="text-[11px] font-normal text-blue-600">{{ __('Branches: {0}', [branches.length]) }}</span>
          </div>
          <select v-model="selectedBranch" class="w-full text-sm font-semibold rounded-lg border-gray-300 p-2 bg-white text-gray-800 shadow-sm">
            <option v-for="b in branches" :key="b.address_name" :value="b.address_name">
              {{ b.branch_title }} {{ b.phone ? ' - ' + b.phone : '' }}
            </option>
          </select>
        </div>
        <div v-else-if="branches.length === 1" class="text-xs text-gray-500 px-1">
          <span class="font-medium">{{ __('Branch') }}:</span> {{ branches[0].branch_title }}
        </div>

        <div class="flex items-center justify-between p-4 rounded-lg border"
             :class="balance > 0 ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'">
          <span class="text-sm text-gray-600">{{ __('Remaining Balance') }}</span>
          <span class="text-3xl font-bold" :class="balance > 0 ? 'text-green-700' : 'text-red-700'">
            {{ loading ? '…' : balance }}
          </span>
        </div>

        <p v-if="!loading && balance <= 0" class="text-sm text-red-600 text-center">
          {{ __('This customer has no voucher balance.') }}
        </p>

        <!-- Quantity stepper (hidden once an OTP has been requested) -->
        <div v-if="!loading && balance > 0 && !otpRequired" class="flex items-center justify-between p-3 rounded-lg border border-gray-200 bg-white">
          <span class="text-sm text-gray-600">{{ __('Vouchers to redeem') }}</span>
          <div class="flex items-center gap-3">
            <button
              class="w-9 h-9 rounded-lg border border-gray-300 text-xl font-bold text-gray-700 flex items-center justify-center disabled:opacity-40 disabled:cursor-not-allowed"
              :disabled="qty <= 1 || redeeming"
              @click="qty = Math.max(1, qty - 1)"
            >−</button>
            <span class="w-10 text-center text-2xl font-bold text-gray-900">{{ qty }}</span>
            <button
              class="w-9 h-9 rounded-lg border border-gray-300 text-xl font-bold text-gray-700 flex items-center justify-center disabled:opacity-40 disabled:cursor-not-allowed"
              :disabled="qty >= balance || redeeming"
              @click="qty = Math.min(balance, qty + 1)"
            >+</button>
          </div>
        </div>

        <!-- OTP verification step -->
        <div v-if="otpRequired" class="p-3 rounded-lg border border-blue-200 bg-blue-50 space-y-2">
          <p class="text-sm text-blue-800 text-center">
            {{ __('A verification code was sent to the customer WhatsApp') }}
            <span v-if="otpMasked" class="font-bold" dir="ltr">{{ otpMasked }}</span>
          </p>
          <input
            v-model="otpCode"
            type="text"
            inputmode="numeric"
            :maxlength="otpDigits"
            :placeholder="__('Enter the {0}-digit code', [otpDigits])"
            class="w-full text-center text-2xl font-bold tracking-[0.4em] py-3 rounded-lg border border-blue-300 focus:outline-none focus:ring-2 focus:ring-blue-400"
            @keyup.enter="doRedeem"
          />
          <p class="text-center text-xs" :class="otpSeconds > 0 ? 'text-blue-600' : 'text-red-600'">
            <span v-if="otpSeconds > 0">{{ __('Code expires in {0}', [otpCountdownText]) }}</span>
            <span v-else>{{ __('Code expired — request a new one.') }}</span>
          </p>
          <button
            class="w-full text-sm font-semibold text-blue-600 hover:text-blue-800 disabled:opacity-50 disabled:cursor-not-allowed"
            :disabled="resending || redeeming"
            @click="resendOtp"
          >
            {{ resending ? __('Resending…') : __('Resend code') }}
          </button>
        </div>

        <div class="flex gap-2">
          <button
            class="flex-1 py-3 rounded-lg text-white font-semibold transition-colors"
            :class="(otpRequired ? (otpCode && !redeeming) : canRedeem) ? 'bg-blue-600 hover:bg-blue-700' : 'bg-gray-300 cursor-not-allowed'"
            :disabled="otpRequired ? (!otpCode || redeeming) : !canRedeem"
            @click="doRedeem"
          >
            {{ redeeming ? __('Processing…') : (otpRequired ? __('Confirm code & redeem') : __('Confirm redeem {0} voucher(s)', [qty])) }}
          </button>
          <button
            class="px-5 py-3 rounded-lg font-semibold text-gray-700 bg-gray-100 hover:bg-gray-200 transition-colors"
            :disabled="redeeming"
            @click="close"
          >
            {{ __('Cancel') }}
          </button>
        </div>
        <p class="text-[11px] text-gray-400 text-center">
          {{ __('No tax invoice is issued on redemption; VAT was collected when the voucher book was purchased.') }}
        </p>
      </template>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch, onBeforeUnmount } from "vue"
import { call } from "frappe-ui"
import { useToast } from "@/composables/useToast"

const props = defineProps({
  modelValue: Boolean,
  posProfile: String,
  openingShift: String,
  customer: [String, Object],
})
const emit = defineEmits(["update:modelValue", "redeemed"])
const { showSuccess, showError } = useToast()

const balance = ref(0)
const qty = ref(1)
const loading = ref(false)
const redeeming = ref(false)

// OTP step (enabled per POS Profile): a code is sent to the customer's WhatsApp
// and must be entered before the redemption is performed.
const otpRequired = ref(false)
const otpCode = ref("")
const otpMasked = ref("")
const otpDigits = ref(5)
const resending = ref(false)

// Countdown for the 2-minute OTP validity window.
const otpSeconds = ref(0)
let otpTimer = null
const otpCountdownText = computed(() => {
  const s = Math.max(0, otpSeconds.value)
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`
})
function startOtpCountdown() {
  stopOtpCountdown()
  otpSeconds.value = 120
  otpTimer = setInterval(() => {
    otpSeconds.value = Math.max(0, otpSeconds.value - 1)
    if (otpSeconds.value <= 0) stopOtpCountdown()
  }, 1000)
}
function stopOtpCountdown() {
  if (otpTimer) { clearInterval(otpTimer); otpTimer = null }
}
onBeforeUnmount(stopOtpCountdown)

/**
 * Pull the REAL server message out of a Frappe/frappe-ui error instead of the
 * generic fallback. Frappe returns thrown messages in `_server_messages`
 * (a JSON array of stringified {message}) or in `messages`; strip any HTML.
 */
function serverError(e, fallback) {
  const strip = (s) => String(s || "").replace(/<[^>]*>?/gm, "").trim()
  try {
    if (e?._server_messages) {
      const arr = JSON.parse(e._server_messages)
      const parts = arr.map((m) => {
        try { const o = JSON.parse(m); return o?.message ?? o } catch { return m }
      })
      const msg = strip(parts.filter(Boolean).join(" — "))
      if (msg) return msg
    }
  } catch (_) { /* ignore */ }
  if (Array.isArray(e?.messages) && e.messages.length) {
    const msg = strip(e.messages.join(" — "))
    if (msg) return msg
  }
  return strip(e?.message) || fallback
}

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
const canRedeem = computed(
  () => !loading.value && !redeeming.value && balance.value > 0 && qty.value >= 1 && qty.value <= balance.value
)

function close() {
  emit("update:modelValue", false)
}

const branches = ref([])
const selectedBranch = ref("")

async function loadBalance() {
  if (!customerId.value) return
  loading.value = true
  try {
    const res = await call("pos_next.api.voucher.get_voucher_balance", {
      customer: customerId.value,
      pos_profile: props.posProfile,
    })
    balance.value = Number((res && (res.message ?? res))?.balance ?? 0)
    qty.value = balance.value > 0 ? 1 : 0

    // Fetch branches (addresses) for the customer
    try {
      const bRes = await call("pos_next.operations.customer_branches.get_customer_branches", {
        customer: customerId.value,
      })
      branches.value = (bRes && (bRes.message ?? bRes)) || []
      if (branches.value.length > 0) {
        selectedBranch.value = branches.value[0].address_name
      } else {
        selectedBranch.value = ""
      }
    } catch (_) {
      branches.value = []
      selectedBranch.value = ""
    }
  } catch (e) {
    balance.value = 0
    showError(serverError(e, __("Could not load voucher balance")))
  } finally {
    loading.value = false
  }
}

async function doRedeem() {
  // In OTP mode the confirm button submits the code; otherwise it needs a
  // valid quantity selection.
  if (!otpRequired.value && !canRedeem.value) return
  if (otpRequired.value && !otpCode.value) {
    showError(__("Enter the verification code sent via WhatsApp"))
    return
  }
  redeeming.value = true
  try {
    const args = {
      pos_profile: props.posProfile,
      customer: customerId.value,
      pos_opening_shift: props.openingShift,
      qty: qty.value,
      branch_address: selectedBranch.value || undefined,
    }
    if (otpCode.value) args.otp_code = otpCode.value
    const res = await call("pos_next.api.voucher.redeem_voucher", args)
    const data = (res && (res.message ?? res)) || {}

    // First call returned a request to verify an OTP instead of redeeming.
    if (data.otp_required) {
      otpRequired.value = true
      otpMasked.value = data.masked_mobile || ""
      if (data.digits) otpDigits.value = Number(data.digits)
      startOtpCountdown()
      showSuccess(__("A verification code was sent to the customer WhatsApp {0}", [otpMasked.value]))
      return
    }

    const used = Number(data.quantity ?? qty.value)
    balance.value = Number(data.balance ?? 0)
    qty.value = balance.value > 0 ? 1 : 0
    resetOtp()
    showSuccess(__("Redeemed {0} voucher(s). Remaining balance: {1}", [used, balance.value]))
    emit("redeemed", data)
    // Always close after a successful redemption; the sale screen resets to the
    // default customer.
    close()
  } catch (e) {
    showError(serverError(e, __("Could not redeem the voucher")))
  } finally {
    redeeming.value = false
  }
}

async function resendOtp() {
  // Re-request a fresh code: call redeem with no otp_code so the server
  // regenerates and resends (attempts reset).
  otpCode.value = ""
  resending.value = true
  try {
    const res = await call("pos_next.api.voucher.redeem_voucher", {
      pos_profile: props.posProfile,
      customer: customerId.value,
      pos_opening_shift: props.openingShift,
      qty: qty.value,
    })
    const data = (res && (res.message ?? res)) || {}
    if (data.otp_required) {
      otpMasked.value = data.masked_mobile || otpMasked.value
      if (data.digits) otpDigits.value = Number(data.digits)
      startOtpCountdown()
      showSuccess(__("A new code was sent to the customer WhatsApp"))
    }
  } catch (e) {
    showError(serverError(e, __("Could not resend the code")))
  } finally {
    resending.value = false
  }
}

function resetOtp() {
  otpRequired.value = false
  otpCode.value = ""
  otpMasked.value = ""
  otpDigits.value = 5
  stopOtpCountdown()
  otpSeconds.value = 0
}

watch(() => props.modelValue, (v) => { if (v) { resetOtp(); loadBalance() } })
</script>
