<template>
	<!--
		The meeting of the area I stand in (#2060), as the big window of the meeting view (#2061):
		resizable at its corners, movable by its title bar, with fullscreen. Leaving the area
		(or Esc, or "Leave") leaves it.
	-->
	<div
		ref="root"
		class="meeting-panel absolute flex flex-col overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-white text-ink-gray-9 shadow-xl"
		:class="{ 'meeting-panel--busy': busy, 'meeting-panel--full': fullscreen }"
		:style="fullscreen ? {} : maximized ? FILL : box"
		role="region"
		:aria-label="__('Meeting {0}', [area.title])"
		data-testid="meeting-panel"
	>
		<header
			class="flex flex-shrink-0 cursor-move select-none items-center gap-2 border-b border-outline-gray-2 px-3 py-2"
			@pointerdown="start('move', $event)"
			@dblclick="toggleFullscreen"
		>
			<FeatherIcon name="video" class="h-4 w-4 flex-shrink-0 text-ink-gray-6" />
			<span class="min-w-0 flex-1 truncate text-sm font-medium">{{ area.title }}</span>
			<button
				type="button"
				class="flex-shrink-0 rounded p-1 text-ink-gray-5 hover:bg-surface-gray-2 hover:text-ink-gray-8"
				:title="fullscreen || maximized ? __('Leave fullscreen') : __('Fullscreen')"
				data-testid="meeting-fullscreen"
				@pointerdown.stop
				@click="toggleFullscreen"
			>
				<FeatherIcon :name="fullscreen || maximized ? 'minimize' : 'maximize'" class="h-4 w-4" />
			</button>
			<button
				type="button"
				class="flex-shrink-0 rounded px-1.5 py-0.5 text-xs text-ink-gray-5 hover:bg-surface-gray-2 hover:text-ink-gray-8"
				:title="__('Leave the meeting')"
				@pointerdown.stop
				@click="$emit('leave')"
			>
				{{ __("Leave (Esc)") }}
			</button>
		</header>
		<VideoCall
			class="min-h-0 flex-1"
			fill
			:domain="area.jitsi_domain"
			:room="area.jitsi_room"
			:display-name="displayName"
			@joined="giveKeysBack"
			@stolen="giveKeysBack"
		/>
		<template v-if="!fullscreen && !maximized">
			<span
				v-for="corner in CORNERS"
				:key="corner"
				class="meeting-panel__handle"
				:class="`meeting-panel__handle--${corner}`"
				:title="__('Drag to resize')"
				:data-testid="`meeting-resize-${corner}`"
				@pointerdown.stop="start(corner, $event)"
			/>
		</template>
	</div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue"
import { FeatherIcon } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"
import VideoCall from "./VideoCall.vue"

const props = defineProps({
	/** { title, jitsi_domain, jitsi_room } */
	area: { type: Object, required: true },
	displayName: { type: String, default: "" },
	/** Size of the stage the window lives in, px */
	bounds: { type: Object, required: true },
	/** Position and size as shares of the stage: { x, y, w, h } (0..1), so it follows the window */
	rect: { type: Object, required: true },
})
const emit = defineEmits(["leave", "update:rect"])

const CORNERS = ["nw", "ne", "sw", "se"]
const MIN_W = 320
const MIN_H = 220

const root = ref(null)
const busy = ref(false)
const fullscreen = ref(false)
// Where the browser refuses fullscreen (some embedded browsers): fill the whole stage instead.
const maximized = ref(false)
const FILL = { left: "0px", top: "0px", width: "100%", height: "100%" }

const px = computed(() => {
	const { width, height } = props.bounds
	const w = Math.max(MIN_W, Math.min(width, props.rect.w * width))
	const h = Math.max(MIN_H, Math.min(height, props.rect.h * height))
	return {
		x: Math.max(0, Math.min(width - w, props.rect.x * width)),
		y: Math.max(0, Math.min(height - h, props.rect.y * height)),
		w,
		h,
	}
})
const box = computed(() => ({
	left: `${px.value.x}px`,
	top: `${px.value.y}px`,
	width: `${px.value.w}px`,
	height: `${px.value.h}px`,
}))

// --- Move (title bar) and resize (corners): pointer drags, the frame's iframe ignores the
// pointer meanwhile (else Jitsi swallows the move events).
let drag = null

function start(kind, event) {
	if (event.button !== 0 || fullscreen.value || maximized.value) return
	event.preventDefault()
	drag = { kind, startX: event.clientX, startY: event.clientY, from: { ...px.value }, target: event.currentTarget }
	busy.value = true
	try {
		event.currentTarget.setPointerCapture(event.pointerId)
	} catch {
		// the window listeners below still follow the pointer
	}
	window.addEventListener("pointermove", onMove)
	window.addEventListener("pointerup", stop)
	window.addEventListener("pointercancel", stop)
}

function onMove(event) {
	if (!drag) return
	const dx = event.clientX - drag.startX
	const dy = event.clientY - drag.startY
	const { width, height } = props.bounds
	let { x, y, w, h } = drag.from
	if (drag.kind === "move") {
		x = Math.max(0, Math.min(width - w, x + dx))
		y = Math.max(0, Math.min(height - h, y + dy))
	} else {
		const right = x + w
		const bottom = y + h
		if (drag.kind.includes("w")) {
			x = Math.max(0, Math.min(right - MIN_W, x + dx))
			w = right - x
		} else w = Math.max(MIN_W, Math.min(width - x, w + dx))
		if (drag.kind.includes("n")) {
			y = Math.max(0, Math.min(bottom - MIN_H, y + dy))
			h = bottom - y
		} else h = Math.max(MIN_H, Math.min(height - y, h + dy))
	}
	emit("update:rect", { x: x / width, y: y / height, w: w / width, h: h / height })
}

function stop() {
	drag = null
	busy.value = false
	window.removeEventListener("pointermove", onMove)
	window.removeEventListener("pointerup", stop)
	window.removeEventListener("pointercancel", stop)
}

// --- Fullscreen: the whole window (title bar and switches stay), Esc leaves it (browser).
function toggleFullscreen() {
	if (maximized.value) {
		maximized.value = false
		return
	}
	if (document.fullscreenElement) {
		document.exitFullscreen?.().catch(() => {})
		return
	}
	const request = root.value?.requestFullscreen?.()
	if (!request) maximized.value = true
	else request.catch(() => (maximized.value = true))
}
function onFullscreenChange() {
	fullscreen.value = document.fullscreenElement === root.value
	if (!fullscreen.value) giveKeysBack()
}

/** Esc: leaves the filled stage first (true), else the page leaves the meeting. */
function exitFill() {
	if (!maximized.value) return false
	maximized.value = false
	return true
}
defineExpose({ exitFill })

onMounted(() => document.addEventListener("fullscreenchange", onFullscreenChange))
onBeforeUnmount(() => {
	stop()
	document.removeEventListener("fullscreenchange", onFullscreenChange)
	if (document.fullscreenElement === root.value) document.exitFullscreen?.().catch(() => {})
})

// Jitsi may focus its frame by itself: the keys belong to Ophice (walking out leaves).
function giveKeysBack() {
	if (document.activeElement?.tagName !== "IFRAME") return
	document.activeElement.blur()
	window.focus()
}
</script>

<style scoped>
.meeting-panel--busy :deep(iframe) {
	pointer-events: none;
}
.meeting-panel--busy {
	user-select: none;
}
.meeting-panel--full {
	border-radius: 0;
}
/* Corner handles: a small grip that shows on hover, a bigger area to grab. */
.meeting-panel__handle {
	position: absolute;
	z-index: 5;
	width: 18px;
	height: 18px;
}
.meeting-panel__handle::after {
	content: "";
	position: absolute;
	width: 10px;
	height: 10px;
	border-color: var(--ink-gray-5);
	border-style: solid;
	border-width: 0;
	opacity: 0.6;
}
.meeting-panel:hover .meeting-panel__handle::after {
	opacity: 1;
}
.meeting-panel__handle--nw {
	left: 0;
	top: 0;
	cursor: nwse-resize;
}
.meeting-panel__handle--nw::after {
	left: 3px;
	top: 3px;
	border-left-width: 2px;
	border-top-width: 2px;
}
.meeting-panel__handle--ne {
	right: 0;
	top: 0;
	cursor: nesw-resize;
}
.meeting-panel__handle--ne::after {
	right: 3px;
	top: 3px;
	border-right-width: 2px;
	border-top-width: 2px;
}
.meeting-panel__handle--sw {
	left: 0;
	bottom: 0;
	cursor: nesw-resize;
}
.meeting-panel__handle--sw::after {
	left: 3px;
	bottom: 3px;
	border-left-width: 2px;
	border-bottom-width: 2px;
}
.meeting-panel__handle--se {
	right: 0;
	bottom: 0;
	cursor: nwse-resize;
}
.meeting-panel__handle--se::after {
	right: 3px;
	bottom: 3px;
	border-right-width: 2px;
	border-bottom-width: 2px;
}
</style>
