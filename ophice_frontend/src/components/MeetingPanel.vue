<template>
	<!--
		The meeting of the area I stand in (#2060), as the big window of the meeting view (#2061):
		resizable at its corners, movable by its title bar, with fullscreen. Leaving the area
		(or Esc, or "Leave") leaves it.
	-->
	<div
		ref="root"
		class="meeting-panel flex flex-col overflow-hidden rounded-xl bg-surface-white text-ink-gray-9 shadow-xl"
		:class="{
			'meeting-panel--busy': busy,
			'meeting-panel--full': fullscreen,
			// Over an open cockpit (#2075) it is fixed to the window; in the floating window it fills it.
			fixed: dock || (floating && !pip),
			relative: pip && !dock,
			absolute: !dock && !floating && !pip,
		}"
		:style="{ ...(dock ? dockStyle : pip ? PIP : fullscreen ? {} : maximized ? FILL : box), '--area-h': hue ?? 220 }"
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
			<!-- Float (#2075): call and chat in a small window on top of everything. -->
			<button
				v-if="canFloat && !pip && !dock"
				type="button"
				class="flex flex-shrink-0 items-center gap-1 rounded px-1.5 py-0.5 text-xs text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-9"
				:title="__('Float: call and chat in a small window on top of everything')"
				data-testid="meeting-float"
				@pointerdown.stop
				@click="$emit('float')"
			>
				<FeatherIcon name="layers" class="h-3.5 w-3.5" />
				{{ __("Float") }}
			</button>
			<!-- Chrome's picture-in-picture (#2078): how to keep the video on top. -->
			<button
				v-if="CHROMIUM"
				type="button"
				class="flex flex-shrink-0 items-center gap-1 rounded px-1.5 py-0.5 text-xs text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-9"
				:class="{ 'bg-surface-gray-2 text-ink-gray-9': pipTip }"
				:title="__('Keep the video on top of all windows')"
				data-testid="pip-tip-button"
				@pointerdown.stop
				@click="pipTip = !pipTip"
			>
				<FeatherIcon name="copy" class="h-3.5 w-3.5" />
				{{ __("On top") }}
			</button>
			<button
				type="button"
				class="flex flex-shrink-0 items-center gap-1 rounded px-1.5 py-0.5 text-xs text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-9"
				:title="__('Open the meeting in its own browser window')"
				data-testid="meeting-popout"
				@pointerdown.stop
				@click="$emit('popout')"
			>
				<FeatherIcon name="external-link" class="h-3.5 w-3.5" />
				{{ __("Own window") }}
			</button>
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
		<!-- meet.jit.si ends embedded calls after 5 minutes (#2078): say so, offer the own window. -->
		<div
			v-if="limitHint && !hintClosed && !poppedOut"
			class="flex flex-shrink-0 items-start gap-2 border-b border-outline-gray-2 bg-surface-amber-1 px-3 py-2 text-xs text-ink-amber-4"
			role="status"
			data-testid="meeting-limit-hint"
		>
			<FeatherIcon name="clock" class="mt-0.5 h-3.5 w-3.5 flex-shrink-0" />
			<span class="min-w-0 flex-1">
				{{ __("Here in Ophice, meet.jit.si ends the call after 5 minutes. In its own window the meeting runs up to 1 h 35 min.") }}
			</span>
			<Button size="sm" variant="solid" @click="$emit('popout')">{{ __("Open in own window") }}</Button>
			<button type="button" class="rounded p-0.5 hover:bg-surface-amber-2" :title="__('Close')" @click="hintClosed = true">
				<FeatherIcon name="x" class="h-3.5 w-3.5" />
			</button>
		</div>
		<PipTip v-if="pipTip" class="absolute right-3 top-12 z-20" @close="closePipTip" />
		<!-- The meeting runs in its own window: no second call here. -->
		<!--
			The meeting runs in its own window (#2078): this space explains how to find it again, keep
			it visible, bring it back or leave. People land here after chatting in Ophice.
		-->
		<div
			v-if="poppedOut"
			class="min-h-0 flex-1 overflow-y-auto p-5 text-sm text-ink-gray-8"
			data-testid="meeting-popped-out"
		>
			<div class="mx-auto flex max-w-md flex-col gap-4">
				<div class="flex items-start gap-3">
					<span
						class="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full"
						:style="{ background: `hsl(${hue ?? 220} 75% 50% / 0.15)`, color: `hsl(${hue ?? 220} 75% 35%)` }"
					>
						<FeatherIcon :name="windowClosed ? 'alert-circle' : 'external-link'" class="h-5 w-5" />
					</span>
					<div>
						<p class="text-base font-semibold text-ink-gray-9">
							{{ windowClosed ? __("The meeting window was closed") : __("Your call runs in its own window") }}
						</p>
						<p class="text-ink-gray-6">
							{{
								windowClosed
									? __("Open it again, or continue the call here in Ophice.")
									: __("You are still in the meeting of {0}. Video and sound are in the separate browser window.", [area.title])
							}}
						</p>
					</div>
				</div>

				<div class="flex flex-wrap gap-2">
					<Button variant="solid" data-testid="meeting-show-window" @click="$emit('popout')">
						<template #prefix><FeatherIcon name="external-link" class="h-4 w-4" /></template>
						{{ windowClosed ? __("Open it again") : __("Show that window") }}
					</Button>
					<Button variant="subtle" data-testid="meeting-bring-back" @click="$emit('bring-back')">
						<template #prefix><FeatherIcon name="corner-down-left" class="h-4 w-4" /></template>
						{{ __("Back into Ophice") }}
					</Button>
				</div>

				<ol v-if="!windowClosed" class="space-y-3">
					<li class="flex gap-3">
						<span class="step">1</span>
						<div>
							<p class="font-medium text-ink-gray-9">{{ __("Can't find the call?") }}</p>
							<p class="text-ink-gray-6">
								{{ __("Click \"Show that window\": it comes to the front.") }}
								{{ isMac ? __("Or press {0} to switch between the browser's windows.", ["⌘ `"]) : __("Or press {0} to switch windows.", ["Alt + Tab"]) }}
							</p>
						</div>
					</li>
					<li v-if="CHROMIUM" class="flex gap-3">
						<span class="step">2</span>
						<div>
							<p class="font-medium text-ink-gray-9">{{ __("Keep the video visible while you work here") }}</p>
							<p class="text-ink-gray-6">
								{{ __("In the call's window, right-click a person's video and choose \"Picture in picture\". If a small menu of the call opens first, right-click again. The video then floats above all windows, also over Ophice.") }}
							</p>
						</div>
					</li>
					<li class="flex gap-3">
						<span class="step">{{ CHROMIUM ? 3 : 2 }}</span>
						<div>
							<p class="font-medium text-ink-gray-9">{{ __("Back into Ophice") }}</p>
							<p class="text-ink-gray-6">
								{{ __("Closes the separate window and continues the call here.") }}
								{{ area.jitsi_domain === "meet.jit.si" ? __("Here meet.jit.si ends the call after 5 minutes.") : "" }}
							</p>
						</div>
					</li>
					<li class="flex gap-3">
						<span class="step">{{ CHROMIUM ? 4 : 3 }}</span>
						<div>
							<p class="font-medium text-ink-gray-9">{{ __("Leaving") }}</p>
							<p class="text-ink-gray-6">
								{{ __("Walk out of the space or press \"Leave\": the separate window closes and the call ends.") }}
							</p>
						</div>
					</li>
				</ol>
			</div>
		</div>
		<VideoCall
			v-else
			class="min-h-0 flex-1"
			fill
			:domain="area.jitsi_domain"
			:room="area.jitsi_room"
			:display-name="displayName"
			@joined="giveKeysBack"
			@stolen="giveKeysBack"
		/>
		<template v-if="!fullscreen && !maximized && !pip && !dock">
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
import { Button, FeatherIcon } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"
import VideoCall from "./VideoCall.vue"
import PipTip from "./PipTip.vue"
import { canFloat } from "../utils/pip.js"

const props = defineProps({
	/** { title, jitsi_domain, jitsi_room } */
	area: { type: Object, required: true },
	displayName: { type: String, default: "" },
	/** Size of the stage the window lives in, px */
	bounds: { type: Object, required: true },
	/** Position and size as shares of the stage: { x, y, w, h } (0..1), so it follows the window */
	rect: { type: Object, required: true },
	/** The space's colour (a hue): the window's frame (#2078). */
	hue: { type: [Number, String], default: null },
	/** Show the 5-minute note (embedded meet.jit.si, #2078). */
	limitHint: { type: Boolean, default: false },
	/** The meeting runs in its own browser window: no embedded call here. */
	poppedOut: { type: Boolean, default: false },
	/** That window was closed by hand (the person is out of the call). */
	windowClosed: { type: Boolean, default: false },
	/** Over an open cockpit (#2075): fixed to the browser window instead of the map's stage. */
	floating: { type: Boolean, default: false },
	/** In the floating (picture-in-picture) window: fills its upper part, no moving or resizing. */
	pip: { type: Boolean, default: false },
	/** Laid over its spot in the mini map (#2075): { left, top, width, height } px; it follows it. */
	dock: { type: Object, default: null },
})
const emit = defineEmits(["leave", "update:rect", "popout", "bring-back", "float"])
const PIP = { width: "100%", height: "58vh", borderRadius: "0" }
const dockStyle = computed(() => ({
	left: `${props.dock.left}px`,
	top: `${props.dock.top}px`,
	width: `${props.dock.width}px`,
	height: `${props.dock.height}px`,
}))
const hintClosed = ref(false)

// Picture-in-picture on a video is Chrome's (and Edge's) own. The tip opens by itself until it was
// closed once; the "On top" button brings it back.
const isMac = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent)
const CHROMIUM = Boolean(navigator.userAgentData?.brands?.some((b) => /Chromium|Google Chrome|Microsoft Edge/.test(b.brand)))
const PIP_TIP_KEY = "phamos_ophice_pip_tip_seen"
function seen() {
	try {
		return localStorage.getItem(PIP_TIP_KEY) === "1"
	} catch {
		return false
	}
}
const pipTip = ref(CHROMIUM && !seen())
function closePipTip() {
	pipTip.value = false
	try {
		localStorage.setItem(PIP_TIP_KEY, "1")
	} catch {
		// private window: it shows again next time
	}
}

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
	if (event.button !== 0 || fullscreen.value || maximized.value || props.pip || props.dock) return
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
/** The window's place on the screen (px), to open the meeting's own window right over it. */
function screenRect() {
	const box = root.value?.getBoundingClientRect()
	if (!box) return null
	// The browser's own bars above the page (tabs, address bar); the sides have no frame to speak of.
	const top = window.screenY + Math.max(0, window.outerHeight - window.innerHeight)
	const left = window.screenX + Math.max(0, (window.outerWidth - window.innerWidth) / 2)
	return {
		left: Math.round(left + box.left),
		top: Math.round(top + box.top),
		width: Math.round(box.width),
		height: Math.round(box.height),
	}
}

defineExpose({ exitFill, screenRect })

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
.step {
	display: flex;
	flex-shrink: 0;
	align-items: center;
	justify-content: center;
	width: 1.5rem;
	height: 1.5rem;
	border-radius: 999px;
	background: hsl(var(--area-h) 75% 50% / 0.15);
	color: hsl(var(--area-h) 75% 35%);
	font-size: 0.75rem;
	font-weight: 600;
}
/* The space's colour around the meeting window (#2078), like the frame around its people and chat. */
.meeting-panel {
	border: 3px solid hsl(var(--area-h) 75% 50%);
	box-shadow: 0 0 18px 4px hsl(var(--area-h) 75% 50% / 0.4), 0 10px 25px rgba(0, 0, 0, 0.25);
}
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
