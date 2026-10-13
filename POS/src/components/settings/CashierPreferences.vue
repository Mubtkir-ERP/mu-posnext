<template>
  <div v-if="modelValue" class="fixed inset-0 z-[310] bg-black/50 flex items-center justify-center p-4" @click.self="emit('update:modelValue', false)">
    <div class="w-full max-w-xl max-h-[90vh] overflow-y-auto bg-white rounded-xl shadow-2xl p-5 space-y-5" dir="auto">
      <div class="flex items-center justify-between">
        <h2 class="font-bold text-xl">{{ __('Cashier Preferences') }}</h2>
        <button class="text-gray-600 text-2xl" @click="emit('update:modelValue', false)">×</button>
      </div>
      <p class="text-sm text-gray-500">{{ __('Device preferences do not change the branch POS Profile or global permissions.') }}</p>
      <div class="space-y-2">
        <label class="font-semibold text-sm">{{ __('Language') }}</label>
        <select class="border rounded w-full p-2" :value="locale" @change="setLanguage($event.target.value)">
          <option v-for="(item,code) in supportedLocales" :key="code" :value="code">{{ item.name || item.label || code }}</option>
        </select>
      </div>
      <div class="border-t pt-4 space-y-3">
        <h3 class="font-bold">{{ __('Product Display') }}</h3>
        <label class="font-semibold text-sm">{{ __('Default product view') }}</label>
        <select class="border rounded w-full p-2" :value="displayMode" @change="setDisplayMode($event.target.value)">
          <option value="grid">{{ __('Grid View') }}</option>
          <option value="list">{{ __('List View') }}</option>
        </select>
        <p class="text-xs text-gray-500">{{ __('This preference is saved on this cashier device and does not change the POS Profile.') }}</p>
      </div>
      <div class="border-t pt-4 space-y-3">
        <label class="flex items-center gap-2"><input type="checkbox" :checked="showItemCode" @change="setShowItemCode($event.target.checked)" /> {{ __('Show Item Code in Product List') }}</label>
        <p class="text-xs text-gray-500">{{ __('The preference is limited to display; barcode and item identifiers remain unchanged.') }}</p>
      </div>
      <div class="border-t pt-4 space-y-3">
        <h3 class="font-bold">{{ __('QZ Tray & Silent Printing') }}</h3>
        <label class="flex items-center gap-2"><input type="checkbox" :checked="posSettings.silentPrint" @change="posSettings.setLocalSilentPrint($event.target.checked)" /> {{ __('Silent Print via QZ Tray') }}</label>
        <p class="text-xs text-gray-500">{{ __('QZ Tray connection, printer choice and certificate setup remain on this cashier device.') }}</p>
        <div class="flex items-center gap-2 text-sm">
          <span :class="qzConnected ? 'text-green-700' : 'text-red-700'">{{ qzConnected ? __('QZ Tray Connected') : __('QZ Tray Not Connected') }}</span>
          <button v-if="!qzConnected" class="border rounded px-3 py-1" :disabled="qzConnecting" @click="handleConnect">{{ __('Connect') }}</button>
        </div>
        <div class="flex gap-2 items-center">
          <select v-model="selectedPrinter" class="flex-1 min-w-0 border rounded p-2 text-sm">
            <option value="">{{ __('Select printer') }}</option>
            <option v-for="item in printers" :key="item" :value="item">{{ item }}</option>
          </select>
          <button class="border rounded px-3 py-2 text-sm" :disabled="loadingPrinters" @click="refreshPrinters">{{ __('Refresh') }}</button>
        </div>
        <p class="text-xs text-gray-600">{{ __('Certificate status') }}: {{ qzCertStatus || __('Unknown') }}</p>
        <div class="flex gap-2 flex-wrap">
          <button class="border rounded px-3 py-2 text-sm" :disabled="certLoading" @click="generateCertificate">{{ __('Generate QZ Certificate') }}</button>
          <button class="border rounded px-3 py-2 text-sm" @click="downloadCertificate">{{ __('Download QZ Certificate') }}</button>
          <a href="https://qz.io/download/" target="_blank" rel="noopener noreferrer" class="underline text-blue-700 text-sm p-2">{{ __('Install QZ Tray') }}</a>
        </div>
      </div>
      <button class="border border-gray-300 rounded px-4 py-2 w-full" @click="emit('open-admin-settings'); emit('update:modelValue', false)">{{ __('System Settings (Manager)') }}</button>
      <button class="bg-blue-600 text-white px-4 py-2 rounded w-full" @click="emit('update:modelValue', false)">{{ __('Close') }}</button>
    </div>
  </div>
</template>
<script setup>
import { ref } from 'vue'
import { useQzTray } from '@/composables/useQzTray'
import { usePOSSettingsStore } from '@/stores/posSettings'
import { useLocale } from '@/composables/useLocale'
const { locale, supportedLocales, changeLocale } = useLocale()
const posSettings = usePOSSettingsStore()
const displayMode = ref(localStorage.getItem('pos_cashier_product_view') === 'list' ? 'list' : 'grid')
const showItemCode = ref(localStorage.getItem('pos_cashier_show_item_code') !== '0')
function setShowItemCode(value) {
  showItemCode.value = Boolean(value)
  localStorage.setItem('pos_cashier_show_item_code', value ? '1' : '0')
  window.dispatchEvent(new CustomEvent('pos-cashier-show-item-code', { detail: Boolean(value) }))
}
function setDisplayMode(value) {
  displayMode.value = value === 'list' ? 'list' : 'grid'
  localStorage.setItem('pos_cashier_product_view', displayMode.value)
  window.dispatchEvent(new CustomEvent('pos-cashier-product-view', { detail: displayMode.value }))
}
const { qzConnected, qzConnecting, qzCertStatus, printers, selectedPrinter, loadingPrinters, certLoading, handleConnect, refreshPrinters, generateCertificate, downloadCertificate } = useQzTray()
defineProps({ modelValue: Boolean })
const emit = defineEmits(['update:modelValue', 'open-admin-settings'])
async function setLanguage(next) { await changeLocale(next) }
</script>

