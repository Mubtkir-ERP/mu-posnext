<template>
	<!-- Icon-Only Sidebar - Hidden on Mobile, Visible on Desktop -->
	<div class="hidden lg:flex w-16 flex-shrink-0 bg-white border-e border-gray-200 flex-col items-center py-4 flex flex-col gap-2">
		<!-- Promotions -->
		<button
			@click="handleMenuClick('promotions')"
			:class="[
				'w-12 h-12 rounded-lg flex items-center justify-center transition-all relative group',
				activeMenu === 'promotions'
					? 'bg-green-100 text-green-600'
					: 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
			]"
			:title="__('Promotions')"
		>
			<FeatherIcon name="tag" class="w-5 h-5" />
			<div class="absolute start-full ms-2 px-2 py-1 bg-gray-900 text-white text-xs rounded opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap z-50">
				{{ __('Promotions') }}
			</div>
		</button>

		<!-- Products -->
		<button
			@click="handleMenuClick('products')"
			:class="[
				'w-12 h-12 rounded-lg flex items-center justify-center transition-all relative group',
				activeMenu === 'products'
					? 'bg-purple-100 text-purple-600'
					: 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
			]"
			:title="__('Products')"
		>
			<FeatherIcon name="package" class="w-5 h-5" />
			<div class="absolute start-full ms-2 px-2 py-1 bg-gray-900 text-white text-xs rounded opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap z-50">
				{{ __('Products') }}
			</div>
		</button>

		<!-- Invoices -->
		<button
			@click="handleMenuClick('invoices')"
			:class="[
				'w-12 h-12 rounded-lg flex items-center justify-center transition-all relative group',
				activeMenu === 'invoices'
					? 'bg-indigo-100 text-indigo-600'
					: 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
			]"
			:title="__('Invoice Management')"
		>
			<FeatherIcon name="file-text" class="w-5 h-5" />
			<div class="absolute start-full ms-2 px-2 py-1 bg-gray-900 text-white text-xs rounded opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap z-50">
				{{ __('Invoice Management') }}
			</div>
		</button>

		<!-- Customer Orders (مشتريات العميل) -->
		<button
			@click="handleMenuClick('customer-orders')"
			class="w-12 h-12 rounded-lg flex items-center justify-center transition-all relative group text-purple-600 hover:bg-purple-50"
			:title="__('Customer Purchases')"
		>
			<FeatherIcon name="clipboard" class="w-5 h-5" />
			<div class="absolute start-full ms-2 px-2 py-1 bg-gray-900 text-white text-xs rounded opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap z-50">
				{{ __('Customer Purchases') }}
			</div>
		</button>

		<!-- Prepaid Voucher Redemption (استبدال قسيمة) -->
		<button
			v-if="showVoucher"
			@click="handleMenuClick('voucher')"
			class="w-12 h-12 rounded-lg flex items-center justify-center transition-all relative group text-indigo-600 hover:bg-indigo-50"
			:title="__('Redeem Voucher')"
		>
			<FeatherIcon name="gift" class="w-5 h-5" />
			<span
				v-if="voucherBalance > 0"
				class="absolute -top-0.5 -end-0.5 min-w-[18px] h-[18px] px-1 rounded-full bg-indigo-600 text-white text-[10px] font-bold flex items-center justify-center shadow"
			>{{ voucherBalance > 99 ? '99+' : voucherBalance }}</span>
			<div class="absolute start-full ms-2 px-2 py-1 bg-gray-900 text-white text-xs rounded opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap z-50">
				{{ __('Redeem Voucher') }}
			</div>
		</button>

		<!-- Cash Disbursement (صرف نقدي) -->
		<button
			v-if="showCash"
			@click="handleMenuClick('cash')"
			class="w-12 h-12 rounded-lg flex items-center justify-center transition-all relative group text-amber-600 hover:bg-amber-50"
			:title="__('Cash Disbursement')"
		>
			<FeatherIcon name="dollar-sign" class="w-5 h-5" />
			<div class="absolute start-full ms-2 px-2 py-1 bg-gray-900 text-white text-xs rounded opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap z-50">
				{{ __('Cash Disbursement') }}
			</div>
		</button>

		<!-- Spacer to push settings to bottom -->
		<div class="flex-1"></div>

		<!-- Divider -->
		<div class="w-8 border-t border-gray-200 my-2"></div>

		<!-- Settings -->
		<button
			@click="handleMenuClick('settings')"
			:class="[
				'w-12 h-12 rounded-lg flex items-center justify-center transition-all relative group',
				activeMenu === 'settings'
					? 'bg-gray-100 text-gray-900'
					: 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
			]"
			:title="__('Settings')"
		>
			<FeatherIcon name="settings" class="w-5 h-5" />
			<div class="absolute start-full ms-2 px-2 py-1 bg-gray-900 text-white text-xs rounded opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap z-50">
				{{ __('Settings') }}
			</div>
		</button>
	</div>
</template>

<script setup>
import { FeatherIcon } from "frappe-ui"
import { ref } from "vue"

defineProps({
	showVoucher: { type: Boolean, default: false },
	showCash: { type: Boolean, default: false },
	voucherBalance: { type: Number, default: 0 },
})

const emit = defineEmits(["menu-clicked"])

const activeMenu = ref("")

function handleMenuClick(menuItem) {
	activeMenu.value = menuItem
	emit("menu-clicked", menuItem)
}
</script>
