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
			}"
			:style="{ ...rectStyle(area), '--area-h': area.color_hue ?? 265 }"
			:title="area.title"
			data-testid="meeting-area"
		>
			<!-- The start space (#2072): where people are beamed in; no meeting, so no Jitsi logo. -->
			<FeatherIcon v-if="area.kind === 'Start'" name="log-in" class="area__start-icon" />
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
			<span class="area__title truncate">{{ area.title }}</span>
			<!-- Where external guests can be (#2081): a marker everyone sees. -->
			<span v-if="area.kind === 'Guest' || area.kind === 'Customer meeting'" class="area__guests" data-testid="area-guest-marker">
				<FeatherIcon :name="area.kind === 'Guest' ? 'user-plus' : 'briefcase'" class="h-3 w-3" />
				{{ area.kind === "Guest" ? __("Guests") : __("Customers") }}
			</span>
			<!-- Resize handles at the corners, only while editing (the layer above takes the pointer). -->
			<template v-if="editing">
				<span v-for="corner in CORNERS" :key="corner" class="area__handle" :class="`area__handle--${corner}`" />
			</template>
		</div>

		<div v-if="draft" class="area area--draft absolute rounded-md" :style="rectStyle(draft)" />

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
import { computed, reactive, ref } from "vue"
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
.area__guests {
	display: inline-flex;
	align-items: center;
	gap: 3px;
	padding: 0 6px;
	border-radius: 999px;
	background: rgba(255, 255, 255, 0.92);
	color: hsl(var(--area-h) 70% 25%);
	font-size: 10px;
	font-weight: 600;
	line-height: 1.6;
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
.area__logo {
	width: 65%;
	max-width: 110px;
	max-height: 50%;
	opacity: 0.9;
	filter: drop-shadow(0 0 2px rgba(0, 0, 0, 0.8)) drop-shadow(0 0 6px hsl(var(--area-h) 70% 25% / 0.8));
	user-select: none;
}
.area__logo-text {
	font-weight: 700;
	font-size: 0.95rem;
	opacity: 0.9;
	text-shadow: 0 0 3px rgba(0, 0, 0, 0.8);
}
.area__title {
	max-width: 95%;
	padding: 1px 6px;
	border-radius: 4px;
	background: hsl(var(--area-h) 65% 22% / 0.85);
	font-size: 11px;
	font-weight: 600;
	line-height: 1.4;
}
</style>
