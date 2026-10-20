<template>
	<!-- Full Page Overlay -->
	<Transition name="fade">
		<div
			v-if="show"
			class="fixed inset-0 bg-black bg-opacity-50 z-[300]"
			@click.self="handleClose"
		>
			<!-- Main Container -->
			<div class="fixed inset-0 flex items-center justify-center p-4 md:p-6">
				<div class="w-full max-w-6xl max-h-[90vh] bg-white rounded-xl shadow-2xl overflow-hidden flex flex-col">
					<!-- Header -->
					<div class="flex items-center justify-between px-6 py-5 border-b bg-gradient-to-r from-blue-50 to-indigo-50">
						<div class="flex items-center gap-3">
							<div class="p-2 bg-blue-100 rounded-lg">
								<svg class="w-6 h-6 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/>
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>
								</svg>
							</div>
							<div>
								<h2 class="text-xl font-bold text-gray-900">{{ __('POS Settings') }}</h2>
								<p class="text-sm text-gray-600 flex items-center mt-0.5">
									<svg class="w-4 h-4 me-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 13.255A23.931 23.931 0 0112 15c-3.183 0-6.22-.62-9-1.745M16 6V4a2 2 0 00-2-2h-4a2 2 0 00-2 2v2m4 6h.01M5 20h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/>
									</svg>
									{{ __('Operational and synchronization settings for current profile') }}
								</p>
							</div>
						</div>
						<div class="flex items-center gap-2">
							<Button
								@click="loadSettings"
								:loading="loading"
								variant="ghost"
								size="sm"
							>
								<template #prefix>
									<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
									</svg>
								</template>
								{{ __('Refresh') }}
							</Button>
							<Button
								@click="saveSettings"
								:loading="saving"
								variant="solid"
								theme="blue"
							>
								<template #prefix>
									<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
									</svg>
								</template>
								{{ __('Save Changes') }}
							</Button>
							<button
								@click="handleClose"
								class="p-2 hover:bg-white/50 rounded-lg transition-colors"
							>
								<svg class="w-5 h-5 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
								</svg>
							</button>
						</div>
					</div>

					<!-- Main Content -->
					<div class="flex-1 overflow-y-auto bg-gray-50">
						<!-- Loading State -->
						<div v-if="loading" class="flex flex-col items-center justify-center py-16">
							<div class="animate-spin rounded-full h-12 w-12 border-b-3 border-blue-500 mb-4"></div>
							<p class="text-sm font-medium text-gray-600">{{ __('Loading settings...') }}</p>
						</div>

						<!-- Settings Form -->
						<div v-else-if="settings.pos_profile || posProfile" class="p-4 md:p-6 flex flex-col gap-5">
							<div class="p-4 rounded-lg bg-indigo-50 border border-indigo-200 text-sm text-indigo-900">
                                {{ __('Pricing, discount, disbursement, and print format permissions are managed in the POS Profile. QZ Tray and silent printing settings remain in Cashier Preferences.') }}
                            </div>
							<!-- Tabs Navigation -->
							<div class="flex p-1 bg-gray-200 rounded-lg self-start">
								<button
									@click="activeTab = 'stock'"
									:class="['px-4 py-2 text-sm font-medium rounded-md transition-all duration-200', activeTab === 'stock' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-600 hover:text-gray-900 hover:bg-gray-200/50']"
								>
									{{ __('Inventory & Sync') }}
								</button>
								<button
									@click="activeTab = 'sales'"
									:class="['px-4 py-2 text-sm font-medium rounded-md transition-all duration-200', activeTab === 'sales' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-600 hover:text-gray-900 hover:bg-gray-200/50']"
								>
									{{ __('Operational Policies') }}
								</button>
								<button
									@click="activeTab = 'customer_display'"
									:class="['px-4 py-2 text-sm font-medium rounded-md transition-all duration-200', activeTab === 'customer_display' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-600 hover:text-gray-900 hover:bg-gray-200/50']"
								>
									{{ __('Customer Display (Secondary Screen)') }}
								</button>
							</div>

							<!-- Stock Settings Section - Prominent -->
							<div v-if="activeTab === 'stock'" class="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
								<div :class="stockSectionClasses.header">
									<div class="flex items-center justify-between">
										<div class="flex items-center gap-3">
											<div :class="stockSectionClasses.iconContainer">
												<svg :class="stockSectionClasses.icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
													<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" :d="icons.warehouse"/>
												</svg>
											</div>
											<div>
												<h3 class="text-lg font-bold text-gray-900">{{ __('Stock Management') }}</h3>
												<p class="text-xs text-gray-600 mt-0.5">{{ __('Configure warehouse and inventory settings') }}</p>
											</div>
										</div>
										<div :class="stockSectionClasses.badge">
											<svg :class="stockSectionClasses.badgeIcon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
												<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" :d="icons.checkCircle"/>
											</svg>
											<span :class="stockSectionClasses.badgeText">{{ __('Stock Controls') }}</span>
										</div>
									</div>
								</div>
								<div class="p-6 flex flex-col gap-6">
									<!-- Warehouse selection is owned by POS Profile (قرار الجرد). -->
									<!-- Negative-stock policy is shown in the POS Settings doctype screen (قرار الجرد: حذف التكرار هنا). -->
									<!-- Background Stock Sync Settings -->
									<div :class="stockSyncSubsectionClasses.container">
										<div class="flex items-center gap-2 mb-4">
											<svg :class="stockSyncSubsectionClasses.icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
												<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
											</svg>
											<h4 class="text-sm font-semibold text-gray-900">{{ __('Background Stock Sync') }}</h4>
											<div v-if="stockSyncStatus.enabled" class="ms-auto flex items-center px-2.5 py-1 bg-green-100 border border-green-300 rounded-full">
												<div class="w-2 h-2 bg-green-500 rounded-full animate-pulse me-2"></div>
												<span class="text-xs font-medium text-green-800">{{ __('Active') }}</span>
											</div>
											<div v-else class="ms-auto flex items-center px-2.5 py-1 bg-gray-100 border border-gray-300 rounded-full">
												<div class="w-2 h-2 bg-gray-400 rounded-full me-2"></div>
												<span class="text-xs font-medium text-gray-600">{{ __('Inactive') }}</span>
											</div>
										</div>

										<div class="flex flex-col gap-4">
											<!-- Enable Sync Toggle -->
											<CheckboxField
												v-model="stockSyncEnabled"
												:label="__('Enable Automatic Stock Sync')"
												:description="__('Periodically sync stock quantities from server in the background (runs in Web Worker)')"
											/>

											<!-- Sync Interval -->
											<div v-if="stockSyncEnabled" class="ps-6 flex flex-col gap-3 border-s-2 border-blue-200">
												<NumberField
													v-model="stockSyncIntervalSeconds"
													:label="__('Sync Interval (seconds)')"
													:description="__('How often to check server for stock updates (minimum 10 seconds)')"
													:min="10"
													:max="300"
													:step="10"
												/>

												<!-- Sync Status Info -->
												<div class="p-3 bg-blue-50 border border-blue-200 rounded-lg">
													<div class="flex items-start gap-2">
														<svg class="w-4 h-4 text-blue-600 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
															<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" :d="icons.info"/>
														</svg>
														<div class="text-xs text-blue-800 flex flex-col gap-1">
															<TranslatedHTML 
																:tag="'p'"
																:inner="stockSyncStatus.enabled 
																	? __('&lt;strong&gt;Status:&lt;/strong&gt; Running')
																	: __('&lt;strong&gt;Status:&lt;/strong&gt; Stopped')"
															/>
															<TranslatedHTML
																:tag="'p'"
																:inner="__('&lt;strong&gt;Items Tracked:&lt;/strong&gt; {0}', [stockSyncStatus.itemCount || 0])"
															/>
															<TranslatedHTML 
																:tag="'p'"
																:inner="stockSyncStatus.warehouse
																	? __('&lt;strong&gt;Warehouse:&lt;/strong&gt; {0}', [stockSyncStatus.warehouse])
																	: __('Warehouse not set')"
															/>
															<TranslatedHTML 
																:tag="'p'"
																:inner="stockSyncStatus.lastSync
																	? __('&lt;strong&gt;Last Sync:&lt;/strong&gt; {0}', [formatSyncTime(stockSyncStatus.lastSync)]) 
																	: __('&lt;strong&gt;Last Sync:&lt;/strong&gt; Never')"
															/>
														</div>
													</div>
												</div>

												<!-- Network Usage Info -->
												<div class="p-3 bg-gray-50 border border-gray-200 rounded-lg">
													<div class="flex items-start gap-2">
														<svg class="w-4 h-4 text-gray-600 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
															<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"/>
														</svg>
														<div class="text-xs text-gray-700">
															<p class="font-medium mb-1">{{ __('Network Usage:') }}</p>
															<p>{{ __('~15 KB per sync cycle') }}</p>
															<p>{{ __('~{0} MB per hour', [Math.round((3600 / stockSyncIntervalSeconds) * 15 / 1024)]) }}</p>
														</div>
													</div>
												</div>
											</div>
										</div>
									</div>
								</div>
							</div>

							<!-- Sales Management Section - Prominent -->
							<div v-if="activeTab === 'sales'" class="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
								<div :class="salesSectionClasses.header">
									<div class="flex items-center justify-between">
										<div class="flex items-center gap-3">
											<div :class="salesSectionClasses.iconContainer">
												<svg :class="salesSectionClasses.icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
													<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" :d="icons.shoppingCart"/>
												</svg>
											</div>
											<div>
												<h3 class="text-lg font-bold text-gray-900">{{ __('Sales Policies') }}</h3>
												<p class="text-xs text-gray-600 mt-0.5">{{ __('Configure pricing, discounts, and sales operations') }}</p>
											</div>
										</div>
										<div :class="salesSectionClasses.badge">
											<svg :class="salesSectionClasses.badgeIcon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
												<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" :d="icons.currency"/>
											</svg>
											<span :class="salesSectionClasses.badgeText">{{ __('Sales Controls') }}</span>
										</div>
									</div>
								</div>
								<div class="p-6 flex flex-col gap-6">
									<!-- Pricing & Discounts -->
									<div :class="pricingSubsectionClasses.container">
										<div class="flex items-center gap-2 mb-4">
											<svg :class="pricingSubsectionClasses.icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
												<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" :d="icons.tag"/>
											</svg>
											<h4 class="text-sm font-semibold text-gray-900">{{ __('Taxes & Calculation') }}</h4>
										</div>
										<div class="flex flex-col gap-3">
											<p class="text-sm text-gray-600">{{ __('Discount, rate edit, and tax inclusive permissions are managed from POS Profile and POS Settings.') }}</p>
										</div>
									</div>

									<!-- Orders: show/hide the order-status selector on invoice cards -->
									<div :class="operationsSubsectionClasses.container">
										<div class="flex items-center gap-2 mb-4">
											<svg :class="operationsSubsectionClasses.icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
												<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" :d="icons.checkCircle"/>
											</svg>
											<h4 class="text-sm font-semibold text-gray-900">{{ __('Orders') }}</h4>
										</div>
										<div class="flex flex-col gap-3">
											<CheckboxField
												v-model="settings.mu_enable_order_status"
												:label="__('Enable Order Status')"
												:description="__('Show order status selector on invoice cards')"
											/>
										</div>
									</div>

									<!-- Printing: Silent Print and QZ printer stay in this original screen (قرار الجرد) -->
									<div :class="operationsSubsectionClasses.container">
										<div class="flex items-center gap-2 mb-4">
											<svg :class="operationsSubsectionClasses.icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
												<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" :d="icons.checkCircle"/>
											</svg>
											<h4 class="text-sm font-semibold text-gray-900">{{ __('Printing') }}</h4>
										</div>
										<div class="flex flex-col gap-3">
											<CheckboxField
												v-model="settings.silent_print"
												:label="__('Silent Print')"
												:description="__('Send receipts directly to a thermal printer via QZ Tray (no browser dialog)')"
											/>

											<!-- QZ Tray Printer Settings (shown when silent print is enabled) -->
											<div v-if="settings.silent_print" class="ps-6 flex flex-col gap-3 border-s-2 border-teal-200">
												<!-- Connection Status -->
												<div class="flex items-center gap-2">
													<div
														class="w-2.5 h-2.5 rounded-full flex-shrink-0"
														:class="qzConnecting ? 'bg-yellow-500 animate-pulse' : qzConnected ? 'bg-green-500' : 'bg-red-500'"
													></div>
													<span
														class="text-xs font-medium"
														:class="qzConnecting ? 'text-yellow-700' : qzConnected ? 'text-green-700' : 'text-red-700'"
													>
														{{ qzConnecting ? __('Connecting to QZ Tray...') : qzConnected ? __('QZ Tray Connected') : __('QZ Tray Not Connected') }}
													</span>
													<button
														v-if="!qzConnected && !qzConnecting"
														@click="handleQzConnect"
														class="ms-auto text-xs px-2 py-1 bg-blue-100 hover:bg-blue-200 text-blue-700 rounded transition-colors"
													>
														{{ __('Retry') }}
													</button>
												</div>

												<!-- Printer Selection -->
												<div class="flex items-end gap-2">
													<div class="flex-1">
														<SelectField
															v-model="selectedPrinter"
															:label="__('Printer')"
															:options="printerOptions"
															:description="qzPrinters.length === 0 && !loadingPrinters ? __('No printers found. Is QZ Tray running?') : ''"
														/>
													</div>
													<button
														@click="handleRefreshPrinters"
														:disabled="loadingPrinters"
														class="px-2 py-2 mb-0.5 bg-gray-100 hover:bg-gray-200 rounded transition-colors"
														:title="__('Refresh printer list')"
													>
														<svg
															class="w-4 h-4 text-gray-600"
															:class="loadingPrinters ? 'animate-spin' : ''"
															fill="none" stroke="currentColor" viewBox="0 0 24 24"
														>
															<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
														</svg>
													</button>
												</div>

												<!-- QZ Certificate Status & Setup -->
												<div
													:class="[
														'p-3 rounded-lg border',
														qzCertStatus === 'trusted'
															? 'bg-green-50 border-green-200'
															: qzCertStatus === 'untrusted'
																? 'bg-red-50 border-red-200'
																: 'bg-amber-50 border-amber-200'
													]"
												>
													<div class="flex items-start gap-2">
														<!-- Icon changes based on status -->
														<svg
															class="w-4 h-4 mt-0.5 flex-shrink-0"
															:class="qzCertStatus === 'trusted' ? 'text-green-600' : qzCertStatus === 'untrusted' ? 'text-red-600' : 'text-amber-600'"
															fill="none" stroke="currentColor" viewBox="0 0 24 24"
														>
															<path v-if="qzCertStatus === 'trusted'" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"/>
															<path v-else stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"/>
														</svg>
														<div class="flex-1">
															<!-- Title with inline status badge -->
															<div class="flex items-center gap-2 mb-1">
																<p
																	class="text-xs font-semibold"
																	:class="qzCertStatus === 'trusted' ? 'text-green-900' : qzCertStatus === 'untrusted' ? 'text-red-900' : 'text-amber-900'"
																>
																	{{ __('Silent Print Certificate') }}
																</p>
																<span
																	v-if="qzCertStatus === 'trusted'"
																	class="inline-flex items-center gap-1 px-1.5 py-0.5 bg-green-100 border border-green-300 rounded-full"
																>
																	<span class="w-1.5 h-1.5 bg-green-500 rounded-full"></span>
																	<span class="text-[10px] font-medium text-green-800">{{ __('Installed') }}</span>
																</span>
																<span
																	v-else-if="qzCertStatus === 'untrusted'"
																	class="inline-flex items-center gap-1 px-1.5 py-0.5 bg-red-100 border border-red-300 rounded-full"
																>
																	<span class="w-1.5 h-1.5 bg-red-500 rounded-full"></span>
																	<span class="text-[10px] font-medium text-red-800">{{ __('Not Installed') }}</span>
																</span>
																<span
																	v-else
																	class="inline-flex items-center gap-1 px-1.5 py-0.5 bg-amber-100 border border-amber-300 rounded-full"
																>
																	<span class="w-1.5 h-1.5 bg-amber-500 rounded-full"></span>
																	<span class="text-[10px] font-medium text-amber-800">{{ __('Checking...') }}</span>
																</span>
															</div>

															<!-- Status message -->
															<p
																v-if="qzCertStatus === 'trusted'"
																class="text-xs text-green-800 leading-relaxed mb-2"
															>
																{{ __('Certificate is installed and signing is active. Print jobs will be sent silently without confirmation dialogs.') }}
															</p>
															<p
																v-else-if="qzCertStatus === 'untrusted'"
																class="text-xs text-red-800 leading-relaxed mb-2"
															>
																{{ __('Certificate is not installed on this machine. Generate a certificate, download it, and import it into QZ Tray.') }}
															</p>
															<p
																v-else
																class="text-xs text-amber-800 leading-relaxed mb-2"
															>
																{{ __('To print without confirmation dialogs, generate a signing certificate and install it on each POS machine.') }}
															</p>

															<!-- Action buttons -->
															<div class="flex items-center gap-2 flex-wrap">
																<button
																	v-if="qzCertStatus !== 'trusted'"
																	@click="handleSetupQzCertificate"
																	:disabled="qzCertLoading"
																	class="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white rounded-md transition-colors bg-amber-600 hover:bg-amber-700 disabled:bg-amber-400"
																>
																	<svg v-if="qzCertLoading" class="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
																		<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
																		<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
																	</svg>
																	<svg v-else class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
																		<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"/>
																	</svg>
																	{{ __('Generate Certificate') }}
																</button>
																<button
																	v-if="qzCertReady"
																	@click="handleDownloadQzCertificate"
																	class="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-blue-600 hover:bg-blue-700 text-white rounded-md transition-colors"
																>
																	<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
																		<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/>
																	</svg>
																	{{ __('Download Certificate') }}
																</button>
															</div>

															<!-- Install instructions (only when cert exists but not trusted yet) -->
															<p v-if="qzCertReady && qzCertStatus !== 'trusted'" class="text-xs mt-2"
																:class="qzCertStatus === 'untrusted' ? 'text-red-700' : 'text-amber-700'"
															>
																{{ __('Download the certificate and import it into QZ Tray, then restart QZ Tray.') }}
															</p>
														</div>
													</div>
												</div>

												<!-- Help text -->
												<div class="p-3 bg-teal-50 border border-teal-200 rounded-lg">
													<div class="flex items-start gap-2">
														<svg class="w-4 h-4 text-teal-600 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
															<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
														</svg>
														<p class="text-xs text-teal-800 leading-relaxed">
															{{ __('QZ Tray must be installed and running on this computer. Download from') }}
															<a href="https://qz.io/download/" target="_blank" class="font-semibold underline">qz.io</a>.
															{{ __('If QZ Tray is unavailable, printing will fall back to the browser dialog.') }}
														</p>
													</div>
												</div>
											</div>
										</div>
									</div>
								</div>
							</div>

							<!-- Customer Display Settings Section -->
							<div
								v-if="activeTab === 'customer_display'"
								class="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden"
							>
								<div class="px-6 py-4 bg-gradient-to-r from-slate-50 via-gray-50 to-zinc-50 border-b border-gray-200">
									<div class="flex items-center justify-between gap-4">
										<div>
											<h3 class="text-lg font-bold text-gray-900">{{ __("Customer Display") }}</h3>
											<p class="text-xs text-gray-600 mt-0.5">{{ __("Configure the second-monitor customer display for this POS Profile") }}</p>
										</div>
										<button type="button" @click="openCustomerDisplay" :disabled="!settings.customer_display_enabled" class="px-4 py-2 rounded-lg bg-gray-900 text-white text-sm font-semibold disabled:opacity-40 disabled:cursor-not-allowed">
											{{ __("Open Customer Display") }}
										</button>
									</div>
								</div>
								<div class="p-6 flex flex-col gap-6">
									<CheckboxField v-model="settings.customer_display_enabled" :label="__('Enable Customer Display')" :description="__('Enable the always-on customer display for this POS Profile')" />

									<div v-if="settings.customer_display_enabled" class="grid grid-cols-1 lg:grid-cols-2 gap-6">
										<div class="rounded-lg border border-gray-200 p-4 flex flex-col gap-3">
											<h4 class="text-sm font-semibold text-gray-900">{{ __("General") }}</h4>
											<label class="text-xs font-medium text-gray-700">{{ __("Company / Display Name") }}<input v-model="settings.customer_display_company_name" class="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm" /></label>
											<label class="text-xs font-medium text-gray-700">{{ __("Welcome Text") }}<input v-model="settings.customer_display_welcome_text" class="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm" /></label>
											<label class="text-xs font-medium text-gray-700">{{ __("POS Location") }}<input v-model="settings.customer_display_pos_location" class="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm" /></label>
											<div class="grid grid-cols-2 gap-3">
												<label class="text-xs font-medium text-gray-700">{{ __("Theme") }}<select v-model="settings.customer_display_theme" class="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm"><option>Dark</option><option>Light</option></select></label>
												<label class="text-xs font-medium text-gray-700">{{ __("Display Layout") }}<select v-model="settings.customer_display_size_mode" class="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm"><option>Auto</option><option>Standard</option><option>Compact</option></select><span class="mt-1 block text-xs text-gray-500">{{ __("Auto adjusts for 7-inch landscape screens (1024x600 or 800x480).") }}</span></label>
												<label class="text-xs font-medium text-gray-700">{{ __("Currency Label") }}<input v-model="settings.customer_display_currency_label" class="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm" /></label>
											</div>
										</div>

										<div class="rounded-lg border border-gray-200 p-4 flex flex-col gap-3">
											<h4 class="text-sm font-semibold text-gray-900">{{ __("Idle & Thank You") }}</h4>
											<label class="text-xs font-medium text-gray-700">{{ __("Idle Display Mode") }}<select v-model="settings.customer_display_idle_mode" class="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm"><option>Welcome</option><option>Image</option><option>Video</option></select></label>
											<label v-if="settings.customer_display_idle_mode === 'Image'" class="text-xs font-medium text-gray-700">{{ __("Promotional Image URL / File") }}<input v-model="settings.customer_display_idle_image" class="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm" /></label>
											<label v-if="settings.customer_display_idle_mode === 'Video'" class="text-xs font-medium text-gray-700">{{ __("Promotional Video URL / File") }}<input v-model="settings.customer_display_idle_video" class="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm" /></label>
											<div class="rounded-lg border border-blue-100 bg-blue-50/60 p-3 flex flex-col gap-3">
												<CheckboxField v-model="settings.customer_display_overlay_enabled" :label="__('Enable Idle Text Overlay')" />
												<template v-if="settings.customer_display_overlay_enabled">
													<label class="text-xs font-medium text-gray-700">{{ __('Overlay Message') }}<textarea v-model="settings.customer_display_overlay_text" rows="2" maxlength="500" class="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm" placeholder="Buy More Pay Less" /></label>
													<div class="grid grid-cols-2 gap-2">
														<label class="text-xs font-medium text-gray-700">{{ __('Style') }}<select v-model="settings.customer_display_overlay_type" class="mt-1 w-full rounded-md border border-gray-300 px-2 py-2"><option>Static</option><option>Scrolling</option></select></label>
														<label class="text-xs font-medium text-gray-700">{{ __('Show On') }}<select v-model="settings.customer_display_overlay_on" class="mt-1 w-full rounded-md border border-gray-300 px-2 py-2"><option>All</option><option>Welcome</option><option>Image</option><option>Video</option></select></label>
														<label class="text-xs font-medium text-gray-700">{{ __('Position') }}<select v-model="settings.customer_display_overlay_position" class="mt-1 w-full rounded-md border border-gray-300 px-2 py-2"><option>Top</option><option>Bottom</option><option>Center</option></select></label>
														<label v-if="settings.customer_display_overlay_type === 'Scrolling'" class="text-xs font-medium text-gray-700">{{ __('Scroll Speed') }}<select v-model="settings.customer_display_overlay_scroll_speed" class="mt-1 w-full rounded-md border border-gray-300 px-2 py-2"><option>Slow</option><option>Normal</option><option>Fast</option></select></label>
														<label class="text-xs font-medium text-gray-700">{{ __('Text Color') }}<input v-model="settings.customer_display_overlay_text_color" type="color" class="mt-1 w-full h-9" /></label>
														<label class="text-xs font-medium text-gray-700">{{ __('Background Color') }}<input v-model="settings.customer_display_overlay_background_color" type="color" class="mt-1 w-full h-9" /></label>
														<label class="text-xs font-medium text-gray-700">{{ __('Background Opacity %') }}<input v-model.number="settings.customer_display_overlay_opacity" type="number" min="0" max="100" class="mt-1 w-full rounded-md border border-gray-300 px-2 py-2" /></label>
														<label class="text-xs font-medium text-gray-700">{{ __('Font Size (px)') }}<input v-model.number="settings.customer_display_overlay_font_size" type="number" min="14" max="72" class="mt-1 w-full rounded-md border border-gray-300 px-2 py-2" /></label>
													</div>
												</template>
											</div>
											<CheckboxField v-model="settings.cd_enable_thank_you" :label="__('Enable Thank You Screen')" />
											<label v-if="settings.cd_enable_thank_you" class="text-xs font-medium text-gray-700">{{ __("Thank You Title") }}<input v-model="settings.customer_display_thank_you_title" class="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm" /></label>
											<label v-if="settings.cd_enable_thank_you" class="text-xs font-medium text-gray-700">{{ __("Thank You Message") }}<input v-model="settings.customer_display_thank_you_message" class="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm" /></label>
											<NumberField v-if="settings.cd_enable_thank_you" v-model="settings.customer_display_thank_you_duration" :label="__('Thank You Duration (Seconds)')" :min="1" :max="60" />
										</div>
									</div>

									<div v-if="settings.customer_display_enabled" class="rounded-lg border border-gray-200 p-4">
										<h4 class="text-sm font-semibold text-gray-900 mb-1">{{ __("Field Visibility") }}</h4>
										<p class="text-xs text-gray-500 mb-4">{{ __("Turn off any information you do not want customers to see. The layout automatically closes empty space.") }}</p>
										<div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
											<CheckboxField v-for="field in customerDisplayVisibilityFields" :key="field.key" v-model="settings[field.key]" :label="__(field.label)" />
										</div>
									</div>

									<div v-if="settings.customer_display_enabled && settings.cd_show_customer_name" class="rounded-lg border border-gray-200 p-4">
										<label class="text-xs font-medium text-gray-700">{{ __("Customer Name Display") }}<select v-model="settings.cd_customer_name_mode" class="mt-1 w-full max-w-xs rounded-md border border-gray-300 px-3 py-2 text-sm"><option>First Name</option><option>Full Name</option><option>Masked</option></select></label>
									</div>
								</div>
							</div>
						</div>

						<!-- Empty State -->
						<div v-else class="flex flex-col items-center justify-center py-16 text-center">
							<svg class="w-16 h-16 text-gray-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/>
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>
							</svg>
							<p class="text-gray-600 font-medium">{{ __('No POS Profile Selected') }}</p>
							<p class="text-gray-500 text-sm mt-1">{{ __('Please select a POS Profile to configure settings') }}</p>
						</div>
					</div>
				</div>
			</div>
		</div>
	</Transition>
</template>

<script setup>
import CheckboxField from "@/components/settings/CheckboxField.vue"
import NumberField from "@/components/settings/NumberField.vue"
import SelectField from "@/components/settings/SelectField.vue"
import { useToast } from "@/composables/useToast"
import { Button, call, createResource } from "frappe-ui"
import { computed, onMounted, onUnmounted, ref, watch } from "vue"
import {
	getSectionHeaderClasses,
	getSubsectionClasses,
	icons,
} from "./settingsConfig"
import { offlineWorker } from "@/utils/offline/workerClient"
import { logger } from "@/utils/logger"
import { usePOSEvents } from "@/composables/usePOSEvents"
import TranslatedHTML from "../common/TranslatedHTML.vue"
import { useQzTray } from "@/composables/useQzTray"
import { resolveTerminalIdentity } from "@/utils/terminalIdentity"

const log = logger.create('POSSettings')
const { detectSettingsChanges, updateSettingsSnapshot, emitStockSyncConfigured } = usePOSEvents()
const { showSuccess, showError } = useToast()

const props = defineProps({
	modelValue: Boolean,
	posProfile: String,
})

const emit = defineEmits(["update:modelValue"])

const show = ref(props.modelValue)

// State
const activeTab = ref('stock')
const customerDisplayVisibilityFields = [
	{ key: "cd_show_company_name", label: "Show Company Name" },
	{ key: "cd_show_welcome_text", label: "Show Welcome Text" },
	{ key: "cd_show_pos_location", label: "Show POS Location" },
	{ key: "cd_show_pos_number", label: "Show POS Number" },
	{ key: "cd_show_product_image", label: "Show Product Image" },
	{ key: "cd_show_item_name", label: "Show Item Name" },
	{ key: "cd_show_barcode", label: "Show Barcode" },
	{ key: "cd_show_quantity", label: "Show Quantity" },
	{ key: "cd_show_original_price", label: "Show Original Price" },
	{ key: "cd_show_discount_amount", label: "Show Discount Amount" },
	{ key: "cd_show_discount_percentage", label: "Show Discount Percentage" },
	{ key: "cd_show_final_price", label: "Show Final Price" },
	{ key: "cd_show_running_qty", label: "Show Running Quantity" },
	{ key: "cd_show_subtotal", label: "Show Subtotal" },
	{ key: "cd_show_total_discount", label: "Show Total Discount" },
	{ key: "cd_show_grand_total", label: "Show Grand Total" },
	{ key: "cd_show_customer_name", label: "Show Customer Name" },
	{ key: "cd_show_loyalty_points", label: "Show Loyalty Points" },
	{ key: "cd_show_loyalty_earned", label: "Show Loyalty Points Earned" },
	{ key: "cd_show_customer_credit", label: "Show Customer Credit" },
	{ key: "cd_show_payment_method", label: "Show Payment Method" },
	{ key: "cd_show_amount_paid", label: "Show Amount Paid" },
	{ key: "cd_show_remaining_balance", label: "Show Remaining Balance" },
	{ key: "cd_show_change", label: "Show Change" },
	{ key: "cd_show_invoice_number", label: "Show Invoice Number" },
]
const loading = ref(true)
const saving = ref(false)
const settings = ref({
	pos_profile: props.posProfile || "",
	enabled: 1,
	silent_print: 0,
	allow_negative_stock: 0,
	_global_allow_negative_stock: 0,
	tax_inclusive: 0,
	enable_auto_stock_sync: 0,
	stock_sync_interval: 60,
	mu_enable_order_status: 1,
	customer_display_enabled: 0,
	customer_display_company_name: "MUBTKIR",
	customer_display_welcome_text: "Welcome",
	customer_display_pos_location: "",
	customer_display_theme: "Dark",
	customer_display_size_mode: "Auto",
	customer_display_currency_label: "SAR",
	customer_display_idle_mode: "Welcome",
	customer_display_idle_image: "",
	customer_display_idle_video: "",
	customer_display_overlay_enabled: 0,
	customer_display_overlay_text: "",
	customer_display_overlay_type: "Scrolling",
	customer_display_overlay_on: "All",
	customer_display_overlay_position: "Bottom",
	customer_display_overlay_text_color: "#FFFFFF",
	customer_display_overlay_background_color: "#000000",
	customer_display_overlay_opacity: 65,
	customer_display_overlay_font_size: 28,
	customer_display_overlay_scroll_speed: "Normal",
	customer_display_thank_you_duration: 5,
	cd_show_company_name: 1,
	cd_show_welcome_text: 1,
	cd_show_pos_location: 1,
	cd_show_pos_number: 1,
	cd_show_product_image: 1,
	cd_show_item_name: 1,
	cd_show_barcode: 1,
	cd_show_quantity: 1,
	cd_show_original_price: 1,
	cd_show_discount_amount: 1,
	cd_show_discount_percentage: 0,
	cd_show_final_price: 1,
	cd_show_running_qty: 1,
	cd_show_subtotal: 1,
	cd_show_total_discount: 1,
	cd_show_grand_total: 1,
	cd_show_customer_name: 1,
	cd_customer_name_mode: "First Name",
	cd_show_loyalty_points: 1,
	cd_show_loyalty_earned: 1,
	cd_show_customer_credit: 1,
	cd_show_payment_method: 1,
	cd_show_amount_paid: 1,
	cd_show_remaining_balance: 1,
	cd_show_change: 1,
	cd_show_invoice_number: 1,
	cd_enable_thank_you: 1,
	customer_display_thank_you_title: "Thank You",
	customer_display_thank_you_message: "Thank you for shopping with us",
})

// Stock Sync Settings (stored in POS Settings; mirrored to localStorage for app startup)
const stockSyncEnabled = ref(false)
const stockSyncIntervalSeconds = ref(60) // Default 60 seconds
const stockSyncStatus = ref({
	enabled: false,
	warehouse: null,
	itemCount: 0,
	intervalMs: 60000,
	lastSync: null,
	running: false
})

// QZ Tray composable
const {
	qzConnected,
	qzConnecting,
	qzCertStatus,
	printers: qzPrinters,
	selectedPrinter,
	loadingPrinters,
	printerOptions,
	certLoading: qzCertLoading,
	certReady: qzCertReady,
	handleConnect: handleQzConnect,
	refreshPrinters: handleRefreshPrinters,
	generateCertificate: handleSetupQzCertificate,
	downloadCertificate: handleDownloadQzCertificate,
} = useQzTray()

// Dynamic classes using configuration helpers (DRY principle)
const stockSectionClasses = computed(() => getSectionHeaderClasses("purple"))
const salesSectionClasses = computed(() => getSectionHeaderClasses("green"))
const stockSyncSubsectionClasses = computed(() => getSubsectionClasses("indigo"))
const pricingSubsectionClasses = computed(() => getSubsectionClasses("emerald"))
const operationsSubsectionClasses = computed(() => getSubsectionClasses("teal"))

// Resources
const settingsResource = createResource({
	url: "pos_next.pos_next.doctype.pos_settings.pos_settings.get_pos_settings",
	makeParams() {
		return {
			pos_profile: props.posProfile,
		}
	},
	onSuccess(data) {
		if (data) {
			Object.assign(settings.value, data)
			settings.value.pos_profile = props.posProfile
			// Stock sync is stored in POS Settings (قرار الجرد)
			stockSyncEnabled.value = Boolean(Number(data.enable_auto_stock_sync || 0))
			stockSyncIntervalSeconds.value = Number(data.stock_sync_interval) || 60
			// Update event system snapshot
			updateSettingsSnapshot(settings.value)
		}
		loading.value = false
	},
	onError(error) {
		loading.value = false
		showError(__("Failed to load settings"))
	},
})

// Watchers
watch(
	() => props.modelValue,
	(val) => {
		show.value = val
		if (val) {
			loadSettings()
		}
	},
)

watch(show, (val) => {
	emit("update:modelValue", val)
})

// Watch for tax_inclusive changes to provide immediate feedback
const originalTaxInclusive = ref(null)
watch(
	() => settings.value.tax_inclusive,
	(newValue, oldValue) => {
		// Store original value on first load
		if (originalTaxInclusive.value === null && oldValue !== undefined) {
			originalTaxInclusive.value = oldValue
		}

		// Only show feedback if value actually changed from original
		if (originalTaxInclusive.value !== null && newValue !== originalTaxInclusive.value) {
			const mode = newValue ? 'inclusive' : 'exclusive'
			log.info(`Tax mode toggled to: ${mode}`)
		}
	}
)

// Methods
function handleClose() {
	show.value = false
}

async function openCustomerDisplay() {
	if (!props.posProfile || !settings.value.customer_display_enabled) return
	const identity = await resolveTerminalIdentity(props.posProfile)
	const terminalId = String(identity?.terminalId || "").trim()
	if (!terminalId) {
		showError(__("Set the Terminal ID in Printer & Cash Drawer Setup first."))
		return
	}
	const terminal = encodeURIComponent(terminalId)
	const url = `/pos/customer-display?profile=${encodeURIComponent(props.posProfile)}&terminal=${terminal}`
	window.open(url, `POSNextCustomerDisplay_${terminalId}`, "popup=yes,width=1280,height=720,resizable=yes")
}

async function loadSettings() {
	if (!props.posProfile) return
	loading.value = true
	settings.value.pos_profile = props.posProfile
	settingsResource.reload()
}

async function saveSettings() {
	if (!props.posProfile) {
		showError(__("POS Profile not found"))
		return
	}

	saving.value = true

	// Capture old settings for change detection
	const oldSettings = { ...settings.value }

	try {
		// Send only fields editable in this screen. Never write back the
		// effective permissions or read-only ERPNext stock mirror returned by GET.
		const editableSettings = {
			silent_print: settings.value.silent_print ? 1 : 0,
			enable_auto_stock_sync: stockSyncEnabled.value ? 1 : 0,
			stock_sync_interval: Number(stockSyncIntervalSeconds.value) || 60,
			mu_enable_order_status: settings.value.mu_enable_order_status ? 1 : 0,
			customer_display_enabled: settings.value.customer_display_enabled ? 1 : 0,
			customer_display_company_name: settings.value.customer_display_company_name || "",
			customer_display_welcome_text: settings.value.customer_display_welcome_text || "",
			customer_display_pos_location: settings.value.customer_display_pos_location || "",
			customer_display_theme: settings.value.customer_display_theme || "Dark",
			customer_display_size_mode: settings.value.customer_display_size_mode || "Auto",
			customer_display_currency_label: settings.value.customer_display_currency_label || "SAR",
			customer_display_idle_mode: settings.value.customer_display_idle_mode || "Welcome",
			customer_display_idle_image: settings.value.customer_display_idle_image || "",
			customer_display_idle_video: settings.value.customer_display_idle_video || "",
			customer_display_overlay_enabled: settings.value.customer_display_overlay_enabled ? 1 : 0,
			customer_display_overlay_text: settings.value.customer_display_overlay_text || "",
			customer_display_overlay_type: settings.value.customer_display_overlay_type || "Scrolling",
			customer_display_overlay_on: settings.value.customer_display_overlay_on || "All",
			customer_display_overlay_position: settings.value.customer_display_overlay_position || "Bottom",
			customer_display_overlay_text_color: settings.value.customer_display_overlay_text_color || "#FFFFFF",
			customer_display_overlay_background_color: settings.value.customer_display_overlay_background_color || "#000000",
			customer_display_overlay_opacity: Number(settings.value.customer_display_overlay_opacity ?? 65),
			customer_display_overlay_font_size: Number(settings.value.customer_display_overlay_font_size ?? 28),
			customer_display_overlay_scroll_speed: settings.value.customer_display_overlay_scroll_speed || "Normal",
			cd_enable_thank_you: settings.value.cd_enable_thank_you ? 1 : 0,
			customer_display_thank_you_title: settings.value.customer_display_thank_you_title || "Thank You",
			customer_display_thank_you_message: settings.value.customer_display_thank_you_message || "Thank you for shopping with us",
			customer_display_thank_you_duration: Number(settings.value.customer_display_thank_you_duration ?? 5),
			cd_show_customer_name: settings.value.cd_show_customer_name ? 1 : 0,
			cd_customer_name_mode: settings.value.cd_customer_name_mode || "First Name",
		}
		for (const field of customerDisplayVisibilityFields) {
			editableSettings[field.key] = settings.value[field.key] ? 1 : 0
		}
		const result = await call(
			"pos_next.pos_next.doctype.pos_settings.pos_settings.update_pos_settings",
			{
				pos_profile: props.posProfile,
				settings: editableSettings,
			},
		)

		if (result) {
			// GET returns effective permissions; reload authoritative values after SAVE.
			Object.assign(settings.value, result)
			settings.value.pos_profile = props.posProfile
			// Update original values after successful save
			originalTaxInclusive.value = result.tax_inclusive
		}

		// Apply the persisted stock-sync configuration on this device
		await applyStockSyncConfig()

		// Detect and emit settings changes through event system
		// This will notify all listeners (POSSale, stock store, cart store, etc.)
		detectSettingsChanges(settings.value, oldSettings)

		showSuccess(__("Settings saved successfully"))
	} catch (error) {
		log.error("Error saving settings:", error)
		showError(error.message || __("Failed to save settings"))
	} finally {
		saving.value = false
	}
}

// Auto-connect and discover printers when silent_print is toggled on
watch(
	() => settings.value.silent_print,
	async (enabled) => {
		if (enabled) {
			await handleQzConnect()
		}
	}
)

// ============================================================================
// STOCK SYNC FUNCTIONS
// ============================================================================

// Load stock sync settings from localStorage
function loadStockSyncSettings() {
	try {
		const saved = localStorage.getItem('pos_stock_sync_settings')
		if (saved) {
			const parsed = JSON.parse(saved)
			stockSyncEnabled.value = parsed.enabled ?? false
			stockSyncIntervalSeconds.value = parsed.intervalSeconds ?? 60
		}
	} catch (error) {
		log.error('Failed to load stock sync settings:', error)
	}
}

// Save stock sync settings to localStorage
function saveStockSyncSettings() {
	try {
		localStorage.setItem('pos_stock_sync_settings', JSON.stringify({
			enabled: stockSyncEnabled.value,
			intervalSeconds: stockSyncIntervalSeconds.value
		}))
	} catch (error) {
		log.error('Failed to save stock sync settings:', error)
	}
}

// Update stock sync status
async function updateStockSyncStatus() {
	try {
		const status = await offlineWorker.getStockSyncStatus()
		stockSyncStatus.value = status
	} catch (error) {
		log.error('Failed to get stock sync status:', error)
	}
}

// Apply stock sync configuration to worker
async function applyStockSyncConfig() {
	try {
		const intervalMs = stockSyncIntervalSeconds.value * 1000

		if (stockSyncEnabled.value) {
			// Configure and start sync
			await offlineWorker.configureStockSync({
				intervalMs
			})
			await offlineWorker.startStockSync()
		} else {
			// Stop sync
			await offlineWorker.stopStockSync()
		}

		// Update status
		await updateStockSyncStatus()

		// Save to localStorage
		saveStockSyncSettings()

		// Emit sync configuration change event
		emitStockSyncConfigured({
			enabled: stockSyncEnabled.value,
			intervalMs: intervalMs
		})
	} catch (error) {
		log.error('Failed to apply stock sync config:', error)
	}
}

// Format sync time for display
function formatSyncTime(timestamp) {
	if (!timestamp) return __('Never')

	const now = Date.now()
	const diff = now - timestamp

	if (diff < 60000) {
		return __('{0}s ago', [Math.floor(diff / 1000)])
	} else if (diff < 3600000) {
		return __('{0}m ago', [Math.floor(diff / 60000)])
	} else {
		const date = new Date(timestamp)
		return date.toLocaleTimeString()
	}
}

// Watch for changes and apply
watch(stockSyncEnabled, () => {
	applyStockSyncConfig()
})

watch(stockSyncIntervalSeconds, () => {
	if (stockSyncEnabled.value) {
		applyStockSyncConfig()
	}
})

// Lifecycle hooks
onMounted(async () => {
	// Load settings
	loadStockSyncSettings()

	// Update status initially
	await updateStockSyncStatus()

	// Poll status every 5 seconds
	const statusInterval = setInterval(() => {
		updateStockSyncStatus()
	}, 5000)

	// Cleanup on unmount
	onUnmounted(() => {
		clearInterval(statusInterval)
	})
})
</script>

<style scoped>
/* Fade transition for overlay */
.fade-enter-active,
.fade-leave-active {
	transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
	opacity: 0;
}
</style>
