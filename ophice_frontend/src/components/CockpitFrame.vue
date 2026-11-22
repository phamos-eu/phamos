<template>
	<!--
		A cockpit inside Ophice (#2073): a full-size frame over the map. Ophice keeps running
		underneath (my chip, the live connection, a call). Same origin, so its address is read here
		and kept in Ophice's address bar: a reload comes back to the same cockpit page.
	-->
	<div class="absolute inset-0 z-40 flex flex-col bg-surface-white" data-testid="cockpit-frame">
		<iframe
			ref="frame"
			:key="frameKey"
			:src="src"
			class="min-h-0 w-full flex-1 border-0"
			:title="__('Cockpit')"
			allow="clipboard-read; clipboard-write; fullscreen"
			@load="onLoad"
		/>
		<!-- Back to the map: the mini map does it (#2074); this button only while Ophice is loading. -->
		<button
			v-if="showBack"
			type="button"
			class="absolute bottom-4 left-4 z-10 flex items-center gap-2 rounded-full border border-outline-gray-2 bg-surface-white py-1.5 pl-1.5 pr-3 text-sm font-medium text-ink-gray-8 shadow-xl hover:bg-surface-gray-2"
			:title="__('Back to the Ophice map (the cockpit stays open)')"
			data-testid="back-to-map"
			@click="$emit('back')"
		>
			<img :src="OPHICE_ICON" alt="" class="h-7 w-7 rounded-full" />
			{{ __("Back to map") }}
		</button>
	</div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from "vue"
import { __ } from "@spa/utils/i18n.js"

const props = defineProps({
	/** where the frame starts, e.g. "/personal-cockpit/todos/plan" */
	src: { type: String, required: true },
	/** a new value reloads the frame at `src`, even when `src` is unchanged */
	frameKey: { type: Number, default: 0 },
	/** the plain "Back to map" button (the mini map replaces it once Ophice is loaded) */
	showBack: { type: Boolean, default: false },
})
const emit = defineEmits(["navigated", "back", "leave"])

const frame = ref(null)
// Served by Frappe, not bundled.
const OPHICE_ICON = "/assets/phamos/manifest/ophice-icon-192.png"
let last = ""
let timer = null

/** "/sales-cockpit/leads?x=1", or "" when the frame can't be read. */
function location() {
	try {
		const where = frame.value?.contentWindow?.location
		// While loading, the frame is at about:blank: not a page yet.
		if (!where || where.protocol === "about:" || !where.pathname.startsWith("/")) return ""
		return `${where.pathname}${where.search}${where.hash}`
	} catch {
		return ""
	}
}

// The cockpits are single-page apps: their own navigation changes the address without a load
// event, so it is checked twice a second.
function check() {
	const now = location()
	if (!now || now === last) return
	last = now
	// Ophice inside Ophice, or the login page: that belongs in the whole window.
	if (now.startsWith("/ophice") || now.startsWith("/login")) return emit("leave", now)
	emit("navigated", now)
}

// Text size (#2091): the cockpit is the same site, so its page scales with Ophice's setting.
const TEXT_SIZE_KEY = "phamos_ophice_text_size"
let baseFont = 0
function applyTextSize(value) {
	try {
		const root = frame.value?.contentDocument?.documentElement
		if (!root) return
		if (!baseFont) baseFont = parseFloat(frame.value.contentWindow.getComputedStyle(root).fontSize) || 16
		const scale = value ?? (parseFloat(localStorage.getItem(TEXT_SIZE_KEY)) || 1)
		root.style.fontSize = scale === 1 ? "" : `${baseFont * scale}px`
	} catch {
		// not readable: the cockpit keeps its own size
	}
}
const onTextSize = (event) => applyTextSize(event.detail)

function onLoad() {
	check()
	baseFont = 0
	applyTextSize()
}

onMounted(() => {
	timer = setInterval(check, 500)
	window.addEventListener("ophice-text-size", onTextSize)
})
onBeforeUnmount(() => {
	clearInterval(timer)
	window.removeEventListener("ophice-text-size", onTextSize)
})

defineExpose({ location })
</script>
