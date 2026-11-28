<template>
	<!--
		Meeting areas (#2060): lightly tinted rectangles with their name and the Jitsi watermark.
		In edit mode a layer over the grid takes the pointer: drag on free grid to draw, drag an area
		to move it, drag its edge or corner to resize it, click an area to edit it.
	-->
	<div class="pointer-events-none absolute inset-0">
		<div
			v-for="area in areas"
			:key="area.name"
			class="area absolute flex flex-col items-center justify-center overflow-hidden rounded-md"
			:class="{
				'area--active': area.name === activeName,
				'area--editing': editing,
				'area--lifted': gesture?.area?.name === area.name && draft,
				'area--start': area.kind === 'Start',
				'area--guests': area.kind === 'Guest' || area.kind === 'Customer meeting',
				'area--phriend': area.kind === 'Phriend',
			}"
			:style="{ ...rectStyle(area), '--area-h': area.color_hue ?? 265, '--tile-px': `${tile}px` }"
			:title="area.title"
			data-testid="meeting-area"
		>
			<!-- Phriend's place (#2053): the ball itself stands on it (Ophice.vue); while editing, a
				 dashed frame to move it by. The anchor in the middle tells Ophice where to pin the ball. -->
			<template v-if="area.kind === 'Phriend'">
				<span class="area__phriend-anchor" data-phriend-anchor />
				<span v-if="editing" class="area__title truncate">{{ __("Phriend") }}</span>
			</template>
			<!-- The start space (#2072): where people are beamed in; no meeting, so no Jitsi logo. -->
			<FeatherIcon v-else-if="area.kind === 'Start'" name="log-in" class="area__start-icon" />
			<!-- A cockpit space (#2076): the cockpit's app icon -->
			<span
				v-else-if="area.kind === 'Cockpit' && COCKPIT_SYMBOLS[area.cockpit] && area.cockpit_color"
				class="area__cockpit-icon"
				:style="{ '--tile': area.cockpit_color }"
				:title="area.cockpit_title || ''"
				data-testid="area-cockpit-icon"
			>
				<FeatherIcon :name="COCKPIT_SYMBOLS[area.cockpit]" class="area__cockpit-symbol" />
			</span>
			<img v-else-if="area.kind === 'Cockpit' && area.cockpit_logo" :src="area.cockpit_logo" alt="" class="area__cockpit-img" />
			<img
				v-else-if="!failedLogos[area.jitsi_domain]"
				:src="`https://${area.jitsi_domain}/images/watermark.svg`"
				alt=""
				class="area__logo"
				draggable="false"
				@error="failedLogos[area.jitsi_domain] = true"
			/>
			<span v-else class="area__logo-text">Jitsi</span>
			<span
				v-if="area.kind !== 'Phriend'"
				class="area__title truncate"
				data-testid="area-title"
				@mouseenter="peekTitle(area, $event)"
				@mouseleave="peek = null"
			>{{ area.title }}</span>
			<!-- Where external guests can be (#2081): a marker everyone sees. -->
			<span v-if="area.kind === 'Guest' || area.kind === 'Customer meeting'" class="area__guests" data-testid="area-guest-marker">
				<FeatherIcon :name="area.kind === 'Guest' ? 'user-plus' : 'briefcase'" class="h-5 w-5" />
				{{ area.kind === "Guest" ? __("Guests") : __("Customers") }}
			</span>
			<!-- Resize handles at the corners, only while editing (the layer above takes the pointer). -->
			<template v-if="editing">
				<span v-for="corner in CORNERS" :key="corner" class="area__handle" :class="`area__handle--${corner}`" />
			</template>
		</div>

		<div v-if="draft" class="area area--draft absolute rounded-md" :style="rectStyle(draft)" />

		<!-- A cut-off name in full while the mouse is on it (#2096), over the label, outside the
			 area's clipping. -->
		<Teleport to="body">
			<span
				v-if="peek"
				ref="peekEl"
				class="area__title area__title--peek"
				:style="{ left: `${peek.x}px`, top: `${peek.y}px`, '--area-h': peek.hue }"
				data-testid="area-title-peek"
			>{{ peek.title }}</span>
		</Teleport>

		<div
			v-if="editing"
			ref="layer"
			class="pointer-events-auto absolute inset-0"
			:style="{ cursor }"
			data-testid="area-edit-layer"
			@pointerdown="onDown"
			@pointermove="onMove"
			@pointerup="onUp"
			@pointercancel="cancel"
		/>
	</div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, toRaw, watch } from "vue"
import { isCutOff } from "../utils/ophiceView.js"
import { FeatherIcon } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"

const props = defineProps({
	areas: { type: Array, default: () => [] },
	tile: { type: Number, required: true },
	cols: { type: Number, required: true },
	rows: { type: Number, required: true },
	editing: { type: Boolean, default: false },
	/** The area whose meeting I am in */
	activeName: { type: String, default: "" },
})

// The full name of a cut-off space name, while the mouse is on it (#2096).
const peek = ref(null)
const peekEl = ref(null)
// Space between the full name and the window's edge.
const PEEK_MARGIN = 8
async function peekTitle(area, event) {
	const label = event.currentTarget
	if (props.editing || !isCutOff(label)) return
	const rect = label.getBoundingClientRect()
	const shown = { title: area.title, x: rect.left + rect.width / 2, y: rect.top + rect.height / 2, hue: area.color_hue ?? 265 }
	peek.value = shown
	// Centred on the label, a long name near the window's left or right edge would itself be
	// cut off: once it is rendered and its width known, keep it inside the window.
	await nextTick()
	// Gone or replaced by another label meanwhile (peek holds a reactive proxy of `shown`).
	if (toRaw(peek.value) !== shown || !peekEl.value) return
	const half = peekEl.value.offsetWidth / 2
	const min = half + PEEK_MARGIN
	const max = window.innerWidth - half - PEEK_MARGIN
	peek.value.x = max < min ? window.innerWidth / 2 : Math.min(Math.max(shown.x, min), max)
}
// Editing, new spaces, or the map moving under the mouse (keys walk and pan, the wheel zooms):
// no stale name left floating where the label no longer is.
watch(() => [props.editing, props.areas], () => (peek.value = null))
const dropPeek = () => (peek.value = null)
const PEEK_ENDERS = ["keydown", "wheel", "pointerdown", "blur"]
onMounted(() => PEEK_ENDERS.forEach((name) => window.addEventListener(name, dropPeek, { passive: true })))
onBeforeUnmount(() => PEEK_ENDERS.forEach((name) => window.removeEventListener(name, dropPeek)))
const emit = defineEmits(["draw", "pick", "change"])

// The symbol of each cockpit's app icon; keep in step with spa_shared/scripts/generate_app_manifests.py.
const COCKPIT_SYMBOLS = {
	"/personal-cockpit": "user",
	"/human-resources-cockpit": "users",
	"/sales-cockpit": "trending-up",
	"/accounting-cockpit": "book-open",
	"/project-management-cockpit": "clipboard",
	"/software-development-cockpit": "code",
	"/general-management-cockpit": "compass",
	"/team-cockpit": "flag",
	"/implementation-cockpit": "layers",
}

const layer = ref(null)
const draft = ref(null)
const failedLogos = reactive({})

function rectStyle(rect) {
	const t = props.tile
	return {
		left: `${rect.x * t}px`,
		top: `${rect.y * t}px`,
		width: `${rect.width * t}px`,
		height: `${rect.height * t}px`,
	}
}

// Areas snap to half tiles (#2067): double the resolution of the chips' grid.
const STEP = 0.5

function tileAt(event) {
	const box = layer.value.getBoundingClientRect()
	const cell = props.tile * STEP
	const x = Math.floor((event.clientX - box.left) / cell) * STEP
	const y = Math.floor((event.clientY - box.top) / cell) * STEP
	return { x: Math.max(0, Math.min(props.cols - STEP, x)), y: Math.max(0, Math.min(props.rows - STEP, y)) }
}

function rectBetween(a, b) {
	const x = Math.min(a.x, b.x)
	const y = Math.min(a.y, b.y)
	return { x, y, width: Math.abs(a.x - b.x) + STEP, height: Math.abs(a.y - b.y) + STEP }
}

// Within this many pixels of an area's edge, a drag resizes instead of moving.
const EDGE_PX = 8
const CORNERS = ["nw", "ne", "sw", "se"]
const CURSORS = { n: "ns-resize", s: "ns-resize", e: "ew-resize", w: "ew-resize", ne: "nesw-resize", sw: "nesw-resize", nw: "nwse-resize", se: "nwse-resize" }

/** { kind: "draw" | "move" | "resize", area, edges, start, clientX, clientY } while the pointer is down. */
const gesture = ref(null)
const hover = ref(null)
const cursor = computed(() => {
	const hit = gesture.value || hover.value
	if (!hit || hit.kind === "draw") return "crosshair"
	if (hit.kind === "move") return gesture.value ? "grabbing" : "grab"
	return CURSORS[hit.edges] || "crosshair"
})

/** What a press at this point would do: resize an area's edge, move an area, or draw. */
function hitAt(event) {
	const box = layer.value.getBoundingClientRect()
	const px = event.clientX - box.left
	const py = event.clientY - box.top
	const t = props.tile
	// The last area wins: it is drawn on top.
	for (const area of [...props.areas].reverse()) {
		const left = area.x * t
		const top = area.y * t
		const right = left + area.width * t
		const bottom = top + area.height * t
		if (px < left - EDGE_PX || px > right + EDGE_PX || py < top - EDGE_PX || py > bottom + EDGE_PX) continue
		const edges =
			(Math.abs(py - top) <= EDGE_PX ? "n" : Math.abs(py - bottom) <= EDGE_PX ? "s" : "") +
			(Math.abs(px - left) <= EDGE_PX ? "w" : Math.abs(px - right) <= EDGE_PX ? "e" : "")
		if (edges) return { kind: "resize", area, edges }
		if (px >= left && px <= right && py >= top && py <= bottom) return { kind: "move", area }
	}
	return { kind: "draw" }
}

function snap(value) {
	return Math.round(value / STEP) * STEP
}

/** The area's new rectangle for a move or resize by (dx, dy) tiles, kept inside the grid. */
function reshape(g, dx, dy) {
	const a = g.area
	if (g.kind === "move") {
		return {
			x: Math.max(0, Math.min(props.cols - a.width, a.x + dx)),
			y: Math.max(0, Math.min(props.rows - a.height, a.y + dy)),
			width: a.width,
			height: a.height,
		}
	}
	let left = a.x
	let top = a.y
	let right = a.x + a.width
	let bottom = a.y + a.height
	if (g.edges.includes("w")) left = Math.max(0, Math.min(right - STEP, left + dx))
	if (g.edges.includes("e")) right = Math.min(props.cols, Math.max(left + STEP, right + dx))
	if (g.edges.includes("n")) top = Math.max(0, Math.min(bottom - STEP, top + dy))
	if (g.edges.includes("s")) bottom = Math.min(props.rows, Math.max(top + STEP, bottom + dy))
	return { x: left, y: top, width: right - left, height: bottom - top }
}

function onDown(event) {
	if (event.button !== 0) return
	gesture.value = { ...hitAt(event), start: tileAt(event), clientX: event.clientX, clientY: event.clientY }
	try {
		// Keeps the drag when the pointer leaves the grid; some pointers can't be captured.
		layer.value.setPointerCapture(event.pointerId)
	} catch {
		// dragging still works while the pointer stays on the grid
	}
}

function onMove(event) {
	const g = gesture.value
	if (!g) {
		hover.value = hitAt(event)
		return
	}
	const moved = Math.hypot(event.clientX - g.clientX, event.clientY - g.clientY)
	if (moved < 4 && !draft.value) return
	if (g.kind === "draw") {
		draft.value = rectBetween(g.start, tileAt(event))
		return
	}
	const cell = props.tile
	const dx = snap((event.clientX - g.clientX) / cell)
	const dy = snap((event.clientY - g.clientY) / cell)
	draft.value = reshape(g, dx, dy)
}

function onUp() {
	const g = gesture.value
	if (!g) return
	const rect = draft.value
	gesture.value = null
	draft.value = null
	if (!rect) {
		// A click without dragging: edit the area under the pointer, if any.
		if (g.area) emit("pick", g.area)
		return
	}
	if (g.kind === "draw") return emit("draw", rect)
	const a = g.area
	if (rect.x !== a.x || rect.y !== a.y || rect.width !== a.width || rect.height !== a.height) emit("change", a, rect)
}

function cancel() {
	gesture.value = null
	draft.value = null
}
</script>

<style scoped>
/* Phriend's place: invisible on the map (Phriend itself stands there), a dashed frame while
   editing. The anchor is one tile in the middle; Ophice pins the ball onto it. */
.area--phriend {
	background: transparent;
	border-color: transparent;
	box-shadow: none;
	overflow: visible;
}
.area--phriend.area--editing {
	border: 2px dashed rgba(255, 255, 255, 0.9);
	background: rgba(0, 0, 0, 0.15);
}
.area__phriend-anchor {
	position: absolute;
	left: 50%;
	top: 50%;
	width: var(--tile-px, 24px);
	height: var(--tile-px, 24px);
	transform: translate(-50%, -50%);
	pointer-events: none;
}
/* Clearly visible on any map (PM: "a little more solid"), each area in its own random color
   (--area-h, a hue; PM 2026-11-22): a solid tint, a firm edge with a light inner line, and
   the white Jitsi watermark with a dark halo. Saturation and lightness stay fixed so the
   title and logo read the same on every color. */
.area {
	--area-h: 265;
	/* Fill in the frame's own color (PM, 2026-11-22), see-through so the map shows. */
	background: hsl(var(--area-h) 70% 42% / 0.32);
	border: 2.5px solid hsl(var(--area-h) 70% 42% / 0.9);
	box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.6), 0 1px 4px rgba(0, 0, 0, 0.35);
	color: #fff;
	gap: 3px;
}
/* The start space: light, with a soft glow, so it reads as an entrance and not as a meeting. */
.area--start {
	background: radial-gradient(ellipse at center, rgba(255, 255, 255, 0.55), hsl(var(--area-h) 70% 70% / 0.25));
	border: 2.5px dotted rgba(255, 255, 255, 0.95);
	box-shadow: 0 0 14px 3px rgba(186, 230, 253, 0.6), inset 0 0 10px rgba(255, 255, 255, 0.6);
}
/* The cockpit's icon, drawn from its tile colour and symbol (PM, 2026-11-22): the tile is
   see-through so it marks the space without sitting on it like a sticker; the white symbol stays
   solid so it reads well. */
.area__cockpit-icon {
	display: flex;
	align-items: center;
	justify-content: center;
	width: 50%;
	max-width: 40px;
	aspect-ratio: 1;
	border-radius: 8px;
	background: color-mix(in srgb, var(--tile) 55%, transparent);
	box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.7), 0 1px 3px rgba(0, 0, 0, 0.3);
}
.area__cockpit-symbol {
	width: 55%;
	height: 55%;
	color: #fff;
	stroke-width: 2.5;
	filter: drop-shadow(0 1px 1px rgba(0, 0, 0, 0.45));
}
/* Fallback for a cockpit without a known symbol: its picture, see-through. */
.area__cockpit-img {
	width: 50%;
	max-width: 40px;
	border-radius: 8px;
	opacity: 0.65;
}
.area__start-icon {
	width: 40%;
	max-width: 28px;
	height: auto;
	color: #fff;
	filter: drop-shadow(0 0 3px rgba(0, 0, 0, 0.7));
}
/* Guest and customer meeting areas: a double edge, so it is clear guests can be here. */
.area--guests {
	border-style: double;
	border-width: 4px;
}
/* "Guests" / "Customers": white on the space itself, no pill, a bit bigger, in the middle of the
   space over the Jitsi logo (PM, 2026-11-22: the marker inverted). The halo keeps it readable. */
.area__guests {
	position: absolute;
	top: 50%;
	left: 50%;
	transform: translate(-50%, -50%);
	z-index: 1;
	display: inline-flex;
	align-items: center;
	justify-content: center;
	gap: 4px;
	white-space: nowrap;
	color: #fff;
	font-size: 13px;
	font-weight: 700;
	line-height: 1.3;
	text-shadow: 0 0 3px rgba(0, 0, 0, 0.8), 0 0 8px hsl(var(--area-h) 70% 20% / 0.8);
	filter: drop-shadow(0 0 2px rgba(0, 0, 0, 0.6));
}
.area--active {
	background: hsl(var(--area-h) 70% 42% / 0.45);
	border-color: hsl(var(--area-h) 70% 35%);
}
.area--editing {
	border-style: dashed;
}
/* The area being moved or resized fades; the dashed draft shows where it goes. */
.area--lifted {
	opacity: 0.35;
}
.area__handle {
	position: absolute;
	width: 9px;
	height: 9px;
	border-radius: 2px;
	background: #fff;
	border: 2px solid hsl(var(--area-h) 70% 35%);
}
.area__handle--nw {
	left: -2px;
	top: -2px;
}
.area__handle--ne {
	right: -2px;
	top: -2px;
}
.area__handle--sw {
	left: -2px;
	bottom: -2px;
}
.area__handle--se {
	right: -2px;
	bottom: -2px;
}
.area--draft {
	background: rgba(124, 58, 237, 0.35);
	border: 2.5px dashed rgb(109, 40, 217);
}
/* The Jitsi watermark, faded (PM, 2026-11-22): it says "meeting" without dominating the map. */
.area__logo {
	width: 65%;
	max-width: 110px;
	max-height: 50%;
	opacity: 0.5;
	filter: drop-shadow(0 0 2px rgba(0, 0, 0, 0.5));
	user-select: none;
}
.area__logo-text {
	font-weight: 700;
	font-size: 0.95rem;
	opacity: 0.9;
	text-shadow: 0 0 3px rgba(0, 0, 0, 0.8);
}
/* Takes the mouse (the layer does not) so a cut-off name can show in full (#2096). */
.area__title {
	pointer-events: auto;
	max-width: 95%;
	padding: 1px 6px;
	border-radius: 4px;
	background: hsl(var(--area-h) 65% 22% / 0.85);
	font-size: 11px;
	font-weight: 600;
	line-height: 1.4;
}
.area__title--peek {
	position: fixed;
	z-index: 60;
	/* One line as long as it fits; a longer name wraps instead of running out of the box, since
	   the peek exists to show the whole name (an ellipsis would cut it again). */
	width: max-content;
	max-width: min(24rem, calc(100vw - 16px));
	transform: translate(-50%, -50%);
	color: #fff;
	white-space: normal;
	overflow-wrap: anywhere;
	text-align: center;
	pointer-events: none;
	box-shadow: 0 2px 8px rgba(0, 0, 0, 0.35);
}
</style>
