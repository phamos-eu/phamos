<template>
	<!-- iOS Add to Home Screen hint -->
	<div
		v-if="iosInstallMessage"
		class="fixed inset-x-3 bottom-6 z-50 rounded-2xl bg-blue-600 text-white shadow-lg p-4"
	>
		<div class="flex items-start justify-between gap-3">
			<div>
				<div class="font-semibold text-sm">Install Lead Scan</div>
				<p class="text-xs mt-1 opacity-90 leading-relaxed">
					Tap
					<FeatherIcon name="share" class="inline h-3.5 w-3.5 mx-0.5 align-text-bottom" />
					Share then <strong>Add to Home Screen</strong> for a one-tap demo.
				</p>
			</div>
			<button
				type="button"
				class="text-white/80 text-lg leading-none"
				aria-label="Dismiss"
				@click="iosInstallMessage = false"
			>
				×
			</button>
		</div>
	</div>

	<Dialog v-model="showDialog">
		<template #body-title>
			<h2 class="text-lg font-bold">Install Lead Scan</h2>
		</template>
		<template #body-content>
			<p class="text-sm text-gray-700">
				Add Lead Scan to your home screen for quick access during demos.
			</p>
		</template>
		<template #actions>
			<Button variant="solid" class="w-full" @click="install">
				<template #prefix>
					<FeatherIcon name="download" class="w-4" />
				</template>
				Install
			</Button>
		</template>
	</Dialog>
</template>

<script setup>
import { ref } from "vue"
import { Dialog, FeatherIcon } from "frappe-ui"

const deferredPrompt = ref(null)
const showDialog = ref(false)
const iosInstallMessage = ref(false)

const isIos = () => {
	const userAgent = window.navigator.userAgent.toLowerCase()
	return /iphone|ipad|ipod/.test(userAgent)
}

const isInStandaloneMode = () =>
	("standalone" in window.navigator && window.navigator.standalone) ||
	window.matchMedia("(display-mode: standalone)").matches

if (isIos() && !isInStandaloneMode()) {
	iosInstallMessage.value = true
}

window.addEventListener("beforeinstallprompt", (e) => {
	e.preventDefault()
	deferredPrompt.value = e
	if (!(isIos() && !isInStandaloneMode())) {
		showDialog.value = true
	}
})

window.addEventListener("appinstalled", () => {
	showDialog.value = false
	deferredPrompt.value = null
	iosInstallMessage.value = false
})

async function install() {
	if (!deferredPrompt.value) return
	deferredPrompt.value.prompt()
	showDialog.value = false
}
</script>
