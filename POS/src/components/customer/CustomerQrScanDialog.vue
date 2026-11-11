<template>
	<Dialog
		v-model="show"
		:options="{ title: __('Scan Customer QR Code'), size: 'sm' }"
	>
		<template #body-content>
			<div class="flex flex-col gap-4">
				<!-- Camera Scanner Viewport -->
				<div class="relative w-full aspect-square max-h-72 bg-black rounded-xl overflow-hidden shadow-inner flex items-center justify-center border border-gray-200">
					<!-- Video element for live camera feed -->
					<video
						ref="videoRef"
						class="w-full h-full object-cover"
						playsinline
						muted
						autoplay
					></video>

					<!-- Animated scanning overlay -->
					<div v-if="cameraActive" class="absolute inset-0 pointer-events-none flex flex-col items-center justify-center p-6">
						<div class="relative w-48 h-48 border-2 border-dashed border-emerald-400/80 rounded-2xl flex items-center justify-center">
							<div class="absolute -top-1 -left-1 w-5 h-5 border-t-4 border-l-4 border-emerald-500 rounded-tl-lg"></div>
							<div class="absolute -top-1 -right-1 w-5 h-5 border-t-4 border-r-4 border-emerald-500 rounded-tr-lg"></div>
							<div class="absolute -bottom-1 -left-1 w-5 h-5 border-b-4 border-l-4 border-emerald-500 rounded-bl-lg"></div>
							<div class="absolute -bottom-1 -right-1 w-5 h-5 border-b-4 border-r-4 border-emerald-500 rounded-br-lg"></div>
							<!-- Laser scan line animation -->
							<div class="absolute inset-x-2 h-0.5 bg-gradient-to-r from-transparent via-emerald-400 to-transparent animate-pulse shadow-[0_0_8px_rgba(52,211,153,0.8)]"></div>
						</div>
						<p class="text-[11px] text-white/80 mt-3 font-medium bg-black/40 px-3 py-1 rounded-full backdrop-blur-sm">
							{{ __('Align QR code inside frame') }}
						</p>
					</div>

					<!-- Camera inactive / Permission state -->
					<div v-if="!cameraActive && !cameraLoading" class="absolute inset-0 bg-gray-900 flex flex-col items-center justify-center p-4 text-center text-white gap-2">
						<svg class="w-10 h-10 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
						</svg>
						<p class="text-xs text-gray-300 font-medium">
							{{ cameraError || __('Camera not available') }}
						</p>
						<button
							type="button"
							@click="startCamera"
							class="text-xs bg-emerald-600 hover:bg-emerald-700 text-white px-3 py-1.5 rounded-lg font-medium transition-colors"
						>
							{{ __('Retry Camera') }}
						</button>
					</div>

					<!-- Camera Loading spinner -->
					<div v-if="cameraLoading" class="absolute inset-0 bg-gray-900/80 flex flex-col items-center justify-center text-white gap-2">
						<div class="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-400"></div>
						<span class="text-xs font-medium">{{ __('Starting camera...') }}</span>
					</div>

					<!-- Camera flip button -->
					<button
						v-if="cameraActive"
						type="button"
						@click="toggleCameraFacing"
						class="absolute top-2 end-2 w-8 h-8 rounded-full bg-black/60 hover:bg-black/80 text-white flex items-center justify-center transition-colors"
						:title="__('Switch Camera')"
					>
						<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
						</svg>
					</button>
				</div>

				<!-- Manual / Hardware Scanner Input -->
				<div class="flex flex-col gap-1.5">
					<label class="text-xs font-semibold text-gray-700">
						{{ __('Or scan with barcode gun / paste code:') }}
					</label>
					<div class="flex gap-2">
						<input
							ref="inputRef"
							v-model="manualCode"
							type="text"
							:placeholder="__('Scan with scanner gun or enter customer...')"
							class="flex-1 px-3 py-2 text-xs border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-500 bg-white"
							:disabled="resolving"
							@keydown.enter.prevent="handleManualSubmit"
						/>
						<Button
							type="button"
							variant="solid"
							theme="green"
							size="sm"
							:loading="resolving"
							:disabled="!manualCode || resolving"
							@click="handleManualSubmit"
						>
							{{ __('Confirm') }}
						</Button>
					</div>
				</div>

				<!-- Error alert if resolving failed -->
				<div
					v-if="resolveError"
					class="p-2.5 bg-red-50 border border-red-200 rounded-xl text-xs text-red-700 flex items-center gap-2"
				>
					<svg class="w-4 h-4 text-red-500 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
					</svg>
					<span>{{ resolveError }}</span>
				</div>
			</div>
		</template>
		<template #actions>
			<Button variant="outline" size="sm" @click="close">
				{{ __('Close') }}
			</Button>
		</template>
	</Dialog>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from "vue"
import { Dialog, Button, call } from "frappe-ui"
import { useToast } from "@/composables/useToast"

const props = defineProps({
	modelValue: Boolean,
	posProfile: String,
})

const emit = defineEmits(["update:modelValue", "scan-success"])

const { showSuccess, showError, showWarning } = useToast()

const show = computed({
	get: () => props.modelValue,
	set: (val) => emit("update:modelValue", val),
})

const videoRef = ref(null)
const inputRef = ref(null)
const manualCode = ref("")
const resolving = ref(false)
const resolveError = ref("")

const cameraActive = ref(false)
const cameraLoading = ref(false)
const cameraError = ref("")
const facingMode = ref("environment")
let stream = null
let scanInterval = null
let barcodeDetector = null

// Initialize native BarcodeDetector if available
if (typeof window !== "undefined" && "BarcodeDetector" in window) {
	try {
		barcodeDetector = new window.BarcodeDetector({
			formats: ["qr_code", "code_128", "code_39", "ean_13"],
		})
	} catch (e) {
		barcodeDetector = null
	}
}

watch(show, async (newVal) => {
	if (newVal) {
		resolveError.value = ""
		manualCode.value = ""
		await nextTick()
		startCamera()
		inputRef.value?.focus()
	} else {
		stopCamera()
	}
})

async function startCamera() {
	if (!navigator?.mediaDevices?.getUserMedia) {
		cameraError.value = "Camera not supported on this browser"
		return
	}

	cameraLoading.value = true
	cameraError.value = ""

	try {
		if (stream) {
			stopCamera()
		}

		stream = await navigator.mediaDevices.getUserMedia({
			video: {
				facingMode: facingMode.value,
				width: { ideal: 1280 },
				height: { ideal: 720 },
			},
			audio: false,
		})

		if (videoRef.value) {
			videoRef.value.srcObject = stream
			await videoRef.value.play()
			cameraActive.value = true
			startScanLoop()
		}
	} catch (err) {
		console.warn("Camera access failed:", err)
		cameraError.value = err.message || "Failed to access camera"
		cameraActive.value = false
	} finally {
		cameraLoading.value = false
	}
}

function stopCamera() {
	if (scanInterval) {
		clearInterval(scanInterval)
		scanInterval = null
	}
	if (stream) {
		for (const track of stream.getTracks()) {
			track.stop()
		}
		stream = null
	}
	if (videoRef.value) {
		videoRef.value.srcObject = null
	}
	cameraActive.value = false
}

function toggleCameraFacing() {
	facingMode.value = facingMode.value === "environment" ? "user" : "environment"
	startCamera()
}

function startScanLoop() {
	if (!barcodeDetector || !videoRef.value) return

	if (scanInterval) clearInterval(scanInterval)

	scanInterval = setInterval(async () => {
		if (!cameraActive.value || resolving.value || !videoRef.value) return
		if (videoRef.value.readyState < 2) return

		try {
			const barcodes = await barcodeDetector.detect(videoRef.value)
			if (barcodes && barcodes.length > 0) {
				const detectedValue = barcodes[0].rawValue
				if (detectedValue) {
					clearInterval(scanInterval)
					scanInterval = null
					await handleQrDetected(detectedValue)
				}
			}
		} catch (e) {
			// Frame detection non-fatal error
		}
	}, 250)
}

async function handleManualSubmit() {
	if (!manualCode.value) return
	await handleQrDetected(manualCode.value.trim())
}

async function handleQrDetected(code) {
	if (resolving.value) return
	resolving.value = true
	resolveError.value = ""

	try {
		const res = await call("pos_next.operations.customer_branches.resolve_customer_qr", {
			qr_text: code,
			pos_profile: props.posProfile || "",
		})

		const data = res && (res.message ?? res)
		if (data && data.success && data.customer) {
			stopCamera()
			emit("scan-success", data)
			close()
			showSuccess(__("Customer '{0}' loaded successfully", [data.customer.customer_name || data.customer.name]))
		} else {
			resolveError.value = data?.error || __("Customer not found")
			if (cameraActive.value) {
				startScanLoop()
			}
		}
	} catch (err) {
		resolveError.value = err?.messages?.[0] || err?.message || __("Failed to resolve customer from QR")
		if (cameraActive.value) {
			startScanLoop()
		}
	} finally {
		resolving.value = false
	}
}

function close() {
	stopCamera()
	show.value = false
}

onBeforeUnmount(() => {
	stopCamera()
})
</script>

