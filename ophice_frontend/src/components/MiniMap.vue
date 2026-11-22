<template>
	<!--
		The mini map over an open cockpit (#2074): the office live, draggable and resizable, with pings
		and quick replies. In a meeting (#2075) it also holds the call and the space's chat: tall, they
		stack under the map; wide, they sit side by side (PM, 2026-11-22). The call and chat themselves
		are laid over the spots kept free here (a moved video window would restart the call).
		"Float" (Chrome, Edge, newer Firefox) puts all of it in a small window on top of everything.
	-->
	<Teleport :to="floatTarget || 'body'" :disabled="!floatTarget">
		<div
			ref="root"
			class="mini-map flex flex-col overflow-hidden rounded-xl border border-outline-gray-3 bg-surface-white text-ink-gray-9 shadow-2xl"
			:class="floatTarget ? 'mini-map--floating' : 'fixed z-[60]'"
			:style="floatTarget ? {} : panelStyle"
			:data-layout="wide ? 'wide' : 'tall'"
			data-testid="mini-map"
		>
			<header
				class="flex flex-shrink-0 select-none items-center gap-1.5 border-b border-outline-gray-2 px-2 py-1.5"
				:class="floatTarget ? '' : 'cursor-move'"
				@pointerdown="startDrag"
			>
				<img :src="OPHICE_ICON" alt="" class="h-4 w-4 rounded" />
				<span class="min-w-0 flex-1 truncate text-xs font-medium">{{ __("Ophice") }}</span>
				<span
					v-if="noticeCount"
					class="rounded-full bg-surface-red-5 px-1.5 text-[10px] font-semibold leading-4 text-ink-white"
					:title="__('{0} notices on the map', [noticeCount])"
				>
					{{ noticeCount }}
				</span>
				<button
					v-if="canFloat && !floatTarget"
					type="button"
					class="rounded p-1 text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-9"
					:title="__('Float: keep the map on top of all windows')"
					data-testid="mini-map-float"
					@pointerdown.stop
					@click="float"
				>
					<FeatherIcon name="copy" class="h-3.5 w-3.5" />
				</button>
				<button
					type="button"
					class="rounded p-1 text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-9"
					:title="__('Back to the map, full screen (the cockpit stays open)')"
					data-testid="mini-map-fullscreen"
					@pointerdown.stop
					@click="$emit('fullscreen')"
				>
					<FeatherIcon name="maximize-2" class="h-3.5 w-3.5" />
				</button>
			</header>

			<div class="flex min-h-0 flex-1 gap-1.5 p-1.5" :class="wide ? 'flex-row' : 'flex-col'">
			<!-- The map and the pings -->
			<div
				ref="mapColumn"
				class="flex min-h-0 min-w-0 flex-col gap-1.5"
				:class="meeting ? (wide ? 'w-1/3 flex-shrink-0' : 'flex-shrink-0') : 'flex-1'"
			>
			<!-- Each part can be folded away (PM, 2026-11-22); folded, the call keeps running. -->
			<button
				v-if="meeting"
				type="button"
				class="mini-map__section-head"
				:aria-expanded="open.map"
				data-testid="mini-map-toggle-map"
				@click="toggle('map')"
			>
				<FeatherIcon :name="open.map ? 'chevron-down' : 'chevron-right'" class="h-3 w-3" />
				<FeatherIcon name="map" class="h-3 w-3" />
				<span>{{ __("Map") }}</span>
			</button>
			<!-- The office, small: a click goes back to the map, full screen -->
			<div
				v-show="open.map || !meeting"
				class="relative flex-shrink-0 cursor-pointer overflow-hidden rounded-lg"
				:style="mapStyle"
				:title="__('Back to the map')"
				data-testid="mini-map-map"
				@click="$emit('fullscreen')"
			>
				<div
					v-for="area in areas"
					:key="area.name"
					class="absolute rounded-sm"
					:style="areaStyle(area)"
				/>
				<span
					v-for="chip in others"
					:key="chip.user"
					class="mini-map__chip absolute rounded-full"
					:class="{ 'opacity-40': chip.offline }"
					:style="chipStyle(chip, chip.guest ? 'rgb(217,119,6)' : `hsl(${ringHue(chip.user)} 80% 45%)`)"
					:title="chip.full_name"
				/>
				<span v-if="me" class="mini-map__chip mini-map__chip--me absolute rounded-full" :style="chipStyle(me, 'rgb(37,99,235)')" :title="__('You')" />
			</div>

			<!-- Pings: newest first -->
			<div
				v-if="pings.length"
				class="min-h-0 space-y-1.5 overflow-y-auto"
				:class="meeting && !wide ? 'max-h-40' : 'max-h-64 flex-1'"
				data-testid="mini-map-pings"
			>
				<div
					v-for="ping in pings"
					:key="ping.id"
					class="rounded-lg bg-surface-gray-1 p-2 text-xs"
					:class="{ 'mini-map__ping--new': ping.fresh }"
					data-testid="mini-map-ping"
				>
					<div class="flex items-start gap-1.5">
						<FeatherIcon :name="ICONS[ping.kind] || 'bell'" class="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-ink-gray-6" />
						<p class="min-w-0 flex-1 text-ink-gray-8">{{ ping.text }}</p>
						<button type="button" class="rounded p-0.5 text-ink-gray-5 hover:bg-surface-gray-3" :title="__('Close')" @click="$emit('dismiss', ping)">
							<FeatherIcon name="x" class="h-3 w-3" />
						</button>
					</div>
					<!-- Answer right here, without leaving the cockpit (PM, 2026-11-22) -->
					<template v-if="ping.kind !== 'reminder'">
						<p v-for="(line, index) in ping.replies || []" :key="index" class="mt-1 text-[11px] text-ink-gray-6">
							{{ __("You: {0}", [line]) }}
						</p>
						<form class="mt-1.5 flex items-center gap-1" @submit.prevent="reply(ping)">
							<input
								v-model="drafts[ping.id]"
								type="text"
								maxlength="1000"
								class="h-7 min-w-0 flex-1 rounded border border-outline-gray-2 bg-surface-white px-2 text-xs text-ink-gray-9"
								:placeholder="ping.kind === 'meeting' ? __('Reply in the meeting chat') : __('Reply')"
								data-testid="mini-map-reply-input"
								@keydown.stop
							/>
							<button
								type="submit"
								class="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded bg-surface-gray-7 text-ink-white disabled:opacity-40"
								:disabled="!(drafts[ping.id] || '').trim() || sending[ping.id]"
								:title="__('Send')"
							>
								<FeatherIcon name="send" class="h-3.5 w-3.5" />
							</button>
						</form>
					</template>
					<!-- Someone walked up: answer without leaving the cockpit -->
					<div v-if="ping.kind === 'walkup'" class="mt-1.5 space-y-1">
						<p class="text-[11px] text-ink-gray-5">{{ __("I'll get back to you in") }}</p>
						<div class="flex flex-wrap gap-1">
							<button
								v-for="minutes in MINUTES"
								:key="minutes"
								type="button"
								class="rounded-full bg-surface-white px-2 py-0.5 text-[11px] font-medium shadow-sm hover:bg-surface-gray-2"
								data-testid="mini-map-reply"
								@click="$emit('reply', ping, minutes)"
							>
								{{ __("{0} min", [minutes]) }}
							</button>
						</div>
						<div class="flex flex-wrap gap-1 pt-0.5">
							<button
								type="button"
								class="rounded-full bg-surface-gray-7 px-2 py-0.5 text-[11px] font-medium text-ink-white hover:opacity-90"
								@click="$emit('open-chat', ping)"
							>
								{{ __("Open the chat") }}
							</button>
							<!-- #2068: depends on the calendar sync -->
							<button
								type="button"
								disabled
								class="cursor-not-allowed rounded-full bg-surface-white px-2 py-0.5 text-[11px] text-ink-gray-4"
								:title="__('Coming soon')"
							>
								{{ __("Book an appointment with me") }} · {{ __("coming soon") }}
							</button>
						</div>
					</div>
					<div v-else-if="ping.kind !== 'reminder'" class="mt-1.5">
						<button
							type="button"
							class="rounded-full bg-surface-white px-2 py-0.5 text-[11px] font-medium shadow-sm hover:bg-surface-gray-2"
							@click="$emit('open-chat', ping)"
						>
							{{ __("Show on the map") }}
						</button>
					</div>
				</div>
			</div>
			</div>
			<!-- In a meeting: the spots the call and the space's chat are laid over (#2075) -->
			<div
				v-if="meeting"
				class="flex min-h-0 min-w-0 flex-col gap-1"
				:class="open.video ? 'flex-1' : 'flex-none'"
			>
				<button type="button" class="mini-map__section-head" :aria-expanded="open.video" data-testid="mini-map-toggle-video" @click="toggle('video')">
					<FeatherIcon :name="open.video ? 'chevron-down' : 'chevron-right'" class="h-3 w-3" />
					<FeatherIcon name="video" class="h-3 w-3" />
					<span v-if="open.video || !wide">{{ open.video ? __("Call") : __("Call (folded, still running)") }}</span>
				</button>
				<div v-show="open.video" ref="videoSlot" class="min-h-0 flex-1 rounded-lg bg-black/80" data-testid="mini-map-video-slot" />
			</div>
			<div
				v-if="meeting"
				class="flex min-h-0 min-w-0 flex-col gap-1"
				:class="open.chat ? (wide ? 'w-1/3 flex-shrink-0' : 'flex-1') : 'flex-none'"
			>
				<button type="button" class="mini-map__section-head" :aria-expanded="open.chat" data-testid="mini-map-toggle-chat" @click="toggle('chat')">
					<FeatherIcon :name="open.chat ? 'chevron-down' : 'chevron-right'" class="h-3 w-3" />
					<FeatherIcon name="message-square" class="h-3 w-3" />
					<span v-if="open.chat || !wide">{{ __("Chat") }}</span>
				</button>
				<div v-show="open.chat" ref="chatSlot" class="min-h-0 flex-1 rounded-lg" data-testid="mini-map-chat-slot" />
			</div>
			</div>
			<!-- Resize from any corner. Tall = a side bar, wide = a bar (PM, 2026-11-22). -->
			<template v-if="!floatTarget">
				<span
					v-for="corner in CORNERS"
					:key="corner"
					class="mini-map__resize"
					:class="`mini-map__resize--${corner}`"
					:title="__('Drag to resize')"
					:data-testid="`mini-map-resize-${corner}`"
					@pointerdown.stop="startResize(corner, $event)"
				/>
			</template>
		</div>
	</Teleport>
	<!-- While moving or resizing: catches the pointer, so the cockpit page and the call (embedded
	     pages, which swallow mouse moves) cannot make the panel jump. -->
	<Teleport to="body">
		<div v-if="grabbing" class="fixed inset-0 z-[80]" :style="{ cursor: grabbing }" data-testid="mini-map-grab-layer" />
	</Teleport>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from "vue"
import { FeatherIcon } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"
import { ringHue } from "../utils/ophiceColor.js"
import { canFloat } from "../utils/pip.js"

const props = defineProps({
	cols: { type: Number, required: true },
	rows: { type: Number, required: true },
	me: { type: Object, default: null },
	others: { type: Array, default: () => [] },
	areas: { type: Array, default: () => [] },
	background: { type: String, default: "" },
	backgroundLayout: { type: Object, default: () => ({ fit: true }) },
	/** [{ id, kind: walkup | message | meeting | reminder, text, user?, fresh? }] */
	pings: { type: Array, default: () => [] },
	noticeCount: { type: Number, default: 0 },
	/** In a meeting: room for the call and the chat (#2075). */
	meeting: { type: Boolean, default: false },
	/** The floating window's body when it floats (Ophice opens it, so the call can go along). */
	floatTarget: { type: Object, default: null },
})
const emit = defineEmits(["fullscreen", "reply", "open-chat", "dismiss", "send", "slots", "float"])

// Replies typed in a ping: sent by the page (Ophice), which knows the chat behind it.
const drafts = reactive({})
const sending = reactive({})
function reply(ping) {
	const text = (drafts[ping.id] || "").trim()
	if (!text || sending[ping.id]) return
	sending[ping.id] = true
	emit("send", ping, text, (ok) => {
		sending[ping.id] = false
		if (ok) drafts[ping.id] = ""
	})
}

// Served by Frappe, not bundled.
const OPHICE_ICON = "/assets/phamos/manifest/ophice-icon-192.png"
const WIDTH = 280
const MIN_W = 240
const MIN_H = 220
const SIZE_KEY = "phamos_ophice_mini_map_size"
const MINUTES = [5, 15, 30, 60]
const ICONS = { walkup: "user", message: "message-circle", meeting: "message-square", reminder: "clock" }
const POS_KEY = "phamos_ophice_mini_map_pos"

// The map fills the width of its column; its height follows the office's shape.
const mapWidth = ref(WIDTH - 12)
const tile = computed(() => {
	let t = mapWidth.value / props.cols
	// Wide: the map must also fit the panel's height (with room for the header).
	if (wide.value) t = Math.min(t, (panelHeight.value - 48) / props.rows)
	return Math.max(2, t)
})
const mapStyle = computed(() => {
	const layout = props.backgroundLayout || { fit: true }
	return {
		width: `${tile.value * props.cols}px`,
		height: `${tile.value * props.rows}px`,
		backgroundColor: "var(--surface-gray-2, #eee)",
		backgroundImage: props.background ? `url("${encodeURI(props.background)}")` : "none",
		backgroundSize: layout.fit ? "cover" : `${layout.scale}% auto`,
		backgroundPosition: layout.fit ? "center" : `${layout.x}% ${layout.y}%`,
		backgroundRepeat: "no-repeat",
	}
})

function areaStyle(area) {
	const t = tile.value
	const h = area.color_hue ?? 220
	return {
		left: `${area.x * t}px`,
		top: `${area.y * t}px`,
		width: `${area.width * t}px`,
		height: `${area.height * t}px`,
		border: `1.5px solid hsl(${h} 70% 45%)`,
		background: `hsl(${h} 70% 45% / 0.25)`,
	}
}

function chipStyle(chip, color) {
	const t = tile.value
	const size = Math.max(7, t * 0.9)
	return {
		width: `${size}px`,
		height: `${size}px`,
		left: `${(chip.x + 0.5) * t - size / 2}px`,
		top: `${(chip.y + 0.5) * t - size / 2}px`,
		background: color,
	}
}

// --- Dragging (place remembered in this browser)

function storedPos() {
	try {
		const pos = JSON.parse(localStorage.getItem(POS_KEY) || "null")
		if (pos && Number.isFinite(pos.x) && Number.isFinite(pos.y)) return pos
	} catch {
		// private window: the default place
	}
	return { x: 16, y: Math.max(16, window.innerHeight - 340) }
}
const pos = reactive(storedPos())
const root = ref(null)
let drag = null

function keepInView() {
	const height = root.value?.offsetHeight || 220
	pos.x = Math.max(4, Math.min(window.innerWidth - size.w - 4, pos.x))
	pos.y = Math.max(4, Math.min(window.innerHeight - Math.min(height, 120), pos.y))
}

function startDrag(event) {
	if (props.floatTarget || event.button !== 0) return
	event.preventDefault()
	drag = { x: event.clientX - pos.x, y: event.clientY - pos.y }
	grabbing.value = "grabbing"
	window.addEventListener("pointermove", onDrag)
	window.addEventListener("pointerup", endDrag, { once: true })
}
function onDrag(event) {
	if (!drag) return
	pos.x = event.clientX - drag.x
	pos.y = event.clientY - drag.y
	keepInView()
}
function endDrag() {
	drag = null
	grabbing.value = ""
	window.removeEventListener("pointermove", onDrag)
	try {
		localStorage.setItem(POS_KEY, JSON.stringify({ x: pos.x, y: pos.y }))
	} catch {
		// private window: the place lasts until the reload
	}
}
window.addEventListener("resize", keepInView)
onBeforeUnmount(() => {
	window.removeEventListener("resize", keepInView)
	window.removeEventListener("pointermove", onDrag)
})

// --- Float: Document Picture-in-Picture, a small window on top of everything (Chrome, Edge,
// newer Firefox; not Safari). The same element moves into it; closing it brings it back.

function float() {
	emit("float")
}

// --- Size (kept in this browser) and layout

function storedSize() {
	try {
		const size = JSON.parse(localStorage.getItem(SIZE_KEY) || "null")
		if (size && Number.isFinite(size.w) && Number.isFinite(size.h)) return size
	} catch {
		// private window
	}
	return { w: 320, h: 640 }
}
const size = reactive(storedSize())
const floatSize = reactive({ w: 0, h: 0 })
const panelHeight = computed(() => (props.floatTarget ? floatSize.h : props.meeting ? size.h : 2000))
const wide = computed(() => {
	if (!props.meeting) return false
	const w = props.floatTarget ? floatSize.w : size.w
	const h = props.floatTarget ? floatSize.h : size.h
	return w > h * 1.3
})
// Which parts are open (kept in this browser).
const OPEN_KEY = "phamos_ophice_mini_map_open"
function storedOpen() {
	try {
		const open = JSON.parse(localStorage.getItem(OPEN_KEY) || "null")
		if (open && typeof open === "object") return { map: open.map !== false, video: open.video !== false, chat: open.chat !== false }
	} catch {
		// private window
	}
	return { map: true, video: true, chat: true }
}
const open = reactive(storedOpen())
function toggle(part) {
	open[part] = !open[part]
	try {
		localStorage.setItem(OPEN_KEY, JSON.stringify({ ...open }))
	} catch {
		// private window
	}
	nextTick(report)
}
// The panel keeps its height while the call or the chat is open; folded, it fits what is left.
const fixedHeight = computed(() => props.meeting && (open.video || open.chat))

const panelStyle = computed(() => ({
	left: `${pos.x}px`,
	top: `${pos.y}px`,
	width: `${size.w}px`,
	// Without a meeting (or with call and chat folded) the height follows the map and pings.
	...(fixedHeight.value ? { height: `${size.h}px` } : { maxHeight: `${window.innerHeight - 16}px` }),
}))

const CORNERS = ["nw", "ne", "sw", "se"]
const CURSORS = { nw: "nwse-resize", se: "nwse-resize", ne: "nesw-resize", sw: "nesw-resize" }
// Set while moving or resizing: the cursor of the layer that catches the pointer.
const grabbing = ref("")
let resize = null

function startResize(corner, event) {
	if (event.button !== 0) return
	event.preventDefault()
	resize = { corner, x: event.clientX, y: event.clientY, from: { x: pos.x, y: pos.y, w: size.w, h: size.h } }
	grabbing.value = CURSORS[corner]
	window.addEventListener("pointermove", onResize)
	window.addEventListener("pointerup", endResize, { once: true })
}

function onResize(event) {
	if (!resize) return
	const { corner, from } = resize
	const dx = event.clientX - resize.x
	const dy = event.clientY - resize.y
	const maxRight = window.innerWidth - 4
	const maxBottom = window.innerHeight - 4
	let { x, y, w, h } = from
	if (corner.includes("e")) w = Math.min(maxRight - x, Math.max(MIN_W, from.w + dx))
	if (corner.includes("w")) {
		// The right edge stays put.
		const right = from.x + from.w
		x = Math.max(4, Math.min(right - MIN_W, from.x + dx))
		w = right - x
	}
	if (corner.includes("s")) h = Math.min(maxBottom - y, Math.max(MIN_H, from.h + dy))
	if (corner.includes("n")) {
		// The bottom edge stays put.
		const bottom = from.y + from.h
		y = Math.max(4, Math.min(bottom - MIN_H, from.y + dy))
		h = bottom - y
	}
	pos.x = x
	pos.y = y
	size.w = w
	size.h = h
}

function endResize() {
	resize = null
	grabbing.value = ""
	window.removeEventListener("pointermove", onResize)
	try {
		localStorage.setItem(SIZE_KEY, JSON.stringify({ w: size.w, h: size.h }))
		localStorage.setItem(POS_KEY, JSON.stringify({ x: pos.x, y: pos.y }))
	} catch {
		// private window
	}
}

// --- The spots for the call and the chat: their place on the screen goes to Ophice, which lays
// the call and the chat over them (and keeps them there while the panel moves or resizes).

const mapColumn = ref(null)
const videoSlot = ref(null)
const chatSlot = ref(null)
function rectOf(el) {
	if (!el) return null
	const r = el.getBoundingClientRect()
	// Folded away: the call stays (out of sight, still running), the chat hides.
	if (!r.width || !r.height) return { hidden: true }
	return { left: r.left, top: r.top, width: r.width, height: r.height }
}
function report() {
	if (mapColumn.value) mapWidth.value = mapColumn.value.clientWidth
	if (props.floatTarget && root.value) {
		floatSize.w = root.value.clientWidth
		floatSize.h = root.value.clientHeight
	}
	emit("slots", props.meeting ? { video: rectOf(videoSlot.value), chat: rectOf(chatSlot.value) } : null)
}
const observer = new ResizeObserver(() => report())
watch([root, mapColumn, videoSlot, chatSlot], (els) => {
	observer.disconnect()
	for (const el of els) if (el) observer.observe(el)
	nextTick(report)
})
watch(
	() => [pos.x, pos.y, size.w, size.h, props.meeting, props.floatTarget, wide.value, open.map, open.video, open.chat],
	() => {
		// A meeting makes the panel taller: keep all of it on the screen.
		if (props.meeting && !props.floatTarget) {
			size.h = Math.min(size.h, window.innerHeight - 8)
			if (pos.y + size.h > window.innerHeight - 4) pos.y = Math.max(4, window.innerHeight - size.h - 4)
		}
		nextTick(report)
	},
	{ immediate: true }
)
// In the floating window (#2075, PM: "keep the snapping and folding there"): its own resizes count
// too, so the call and chat stay on their spots and the tall/wide layout follows the window.
let floatWindow = null
watch(
	() => props.floatTarget,
	(body) => {
		floatWindow?.removeEventListener("resize", report)
		floatWindow = body?.ownerDocument?.defaultView || null
		floatWindow?.addEventListener("resize", report)
		nextTick(report)
	},
	{ immediate: true }
)
onBeforeUnmount(() => {
	observer.disconnect()
	floatWindow?.removeEventListener("resize", report)
	emit("slots", null)
})
</script>

<style scoped>
.mini-map__chip {
	box-shadow: 0 0 0 1.5px #fff, 0 1px 2px rgba(0, 0, 0, 0.5);
	transition: left 160ms linear, top 160ms linear;
}
.mini-map__chip--me {
	box-shadow: 0 0 0 2px #fff, 0 0 6px 2px rgba(59, 130, 246, 0.8);
	z-index: 1;
}
.mini-map--floating {
	width: 100%;
	height: 100vh;
	border-radius: 0;
	border: 0;
}
.mini-map__section-head {
	display: flex;
	flex-shrink: 0;
	align-items: center;
	gap: 4px;
	padding: 2px 4px;
	border-radius: 6px;
	font-size: 11px;
	font-weight: 500;
	color: var(--ink-gray-6, #666);
	text-align: left;
	white-space: nowrap;
}
.mini-map__section-head:hover {
	background: var(--surface-gray-2, #f3f3f3);
	color: var(--ink-gray-9, #111);
}
.mini-map__resize {
	position: absolute;
	width: 16px;
	height: 16px;
	z-index: 2;
}
.mini-map__resize--nw {
	left: 0;
	top: 0;
	cursor: nwse-resize;
}
.mini-map__resize--ne {
	right: 0;
	top: 0;
	cursor: nesw-resize;
}
.mini-map__resize--sw {
	left: 0;
	bottom: 0;
	cursor: nesw-resize;
}
.mini-map__resize--se {
	right: 0;
	bottom: 0;
	cursor: nwse-resize;
	background: linear-gradient(135deg, transparent 50%, var(--outline-gray-4, #999) 50%, transparent 60%, transparent 70%, var(--outline-gray-4, #999) 70%, transparent 80%);
}
</style>
