<template>
	<!--
		Meeting areas (#2060): lightly tinted rectangles, ellipses or polygons (#2144) with their name
		and the Jitsi watermark. In edit mode a layer over the grid takes the pointer: drag on free
		grid to draw a rectangle, click on free grid to set a polygon's corners (click the first one,
		or Enter, to close it; Esc cancels, Backspace takes the last one back), drag an area to move
		it, drag its edge or corner to resize it, drag a polygon's corner, click its edge to add one,
		double-click a corner to remove it, click an area to edit it.
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
				'area--ellipse': shapeOf(area) === 'Ellipse',
				'area--polygon': shapeOf(area) === 'Polygon',
			}"
			:style="{ ...rectStyle(area), '--area-h': area.color_hue ?? 265, '--tile-px': `${tile}px` }"
			:title="area.title"
			data-testid="meeting-area"
		>
			<!-- A polygon (#2144): fill and edge as SVG; the box itself stays clear. -->
			<svg
				v-if="shapeOf(area) === 'Polygon'"
				class="area__shape"
				:viewBox="`0 0 ${area.width} ${area.height}`"
				preserveAspectRatio="none"
				aria-hidden="true"
			>
				<polygon :points="svgPoints(area)" vector-effect="non-scaling-stroke" />
			</svg>
			<div :style="contentStyle(area)">
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
			</div>
			<!-- Handles, only while editing (the layer above takes the pointer): a polygon's corners,
				 else the box's corners. -->
			<template v-if="editing && shapeOf(area) === 'Polygon'">
				<span
					v-for="(point, index) in pointsOf(area)"
					:key="index"
					class="area__handle area__handle--point"
					:style="{ left: `${(point[0] - area.x) * tile}px`, top: `${(point[1] - area.y) * tile}px` }"
				/>
			</template>
			<template v-else-if="editing">
				<span v-for="corner in CORNERS" :key="corner" class="area__handle" :class="`area__handle--${corner}`" />
			</template>
		</div>

		<div
			v-if="draft && shapeOf(draft) !== 'Polygon'"
			class="area area--draft absolute"
			:class="shapeOf(draft) === 'Ellipse' ? 'rounded-full' : 'rounded-md'"
			:style="rectStyle(draft)"
		/>
		<!-- A polygon being reshaped, or the corners set so far while drawing one (in tiles). -->
		<svg
			v-if="(draft && shapeOf(draft) === 'Polygon') || pen"
			class="area-pen pointer-events-none absolute inset-0 h-full w-full overflow-visible"
			:viewBox="`0 0 ${cols} ${rows}`"
			preserveAspectRatio="none"
			aria-hidden="true"
		>
			<polygon
				v-if="draft && shapeOf(draft) === 'Polygon'"
				:points="pointsOf(draft).map((p) => p.join(',')).join(' ')"
				class="area-pen__shape"
				:class="{ 'area-pen__shape--bad': selfCrossing(pointsOf(draft)) }"
				vector-effect="non-scaling-stroke"
			/>
			<template v-if="pen">
				<polyline :points="penLine" class="area-pen__line" :class="{ 'area-pen__line--bad': penCrosses }" vector-effect="non-scaling-stroke" />
				<circle
					v-for="(point, index) in pen.points"
					:key="index"
					:cx="point[0]"
					:cy="point[1]"
					:r="index === 0 && pen.points.length >= 3 ? 10 / tile : 6 / tile"
					class="area-pen__corner"
					:class="{ 'area-pen__corner--close': index === 0 && pen.points.length >= 3 }"
				/>
			</template>
		</svg>
		<p v-if="pen" class="area-pen__hint" data-testid="area-pen-hint">
			{{ __("Click to set corners · click the first corner or press Enter to close · Backspace: last corner back · Esc: cancel") }}
		</p>

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
			@dblclick="onDoubleClick"
		/>
	</div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, toRaw, watch } from "vue"
import { isCutOff } from "../utils/ophiceView.js"
import { FeatherIcon } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"
import { boxOf, contains, labelPoint, MAX_POINTS, nearestOnSegment, pointsOf, segmentDistance, selfCrossing, shapeOf, svgPoints } from "../utils/ophiceShapes.js"

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

// labelPoint samples the whole polygon, and the layer re-renders on every pointer move (hover):
// work it out once per area list, not per frame.
const labelPoints = computed(() => {
	const points = new Map()
	for (const area of props.areas) if (shapeOf(area) === "Polygon") points.set(area, labelPoint(area))
	return points
})

// Name and logo: centred in the box, or for an L-shaped polygon on a spot inside it (#2144).
function contentStyle(area) {
	if (shapeOf(area) !== "Polygon") return { display: "contents" }
	const [lx, ly] = labelPoints.value.get(area) || labelPoint(area)
	const t = props.tile
	return {
		position: "absolute",
		left: `${(lx - area.x) * t}px`,
		top: `${(ly - area.y) * t}px`,
		transform: "translate(-50%, -50%)",
		display: "flex",
		flexDirection: "column",
		alignItems: "center",
		gap: "3px",
		width: `${Math.max(2, area.width) * t}px`,
		maxWidth: `${area.width * t}px`,
	}
}

// Areas snap to half tiles (#2067): double the resolution of the chips' grid.
const STEP = 0.5

/** The nearest half-tile corner to the pointer: where a polygon's corner goes. */
function cornerAt(event) {
	const box = layer.value.getBoundingClientRect()
	const x = snap((event.clientX - box.left) / props.tile)
	const y = snap((event.clientY - box.top) / props.tile)
	return [Math.max(0, Math.min(props.cols, x)), Math.max(0, Math.min(props.rows, y))]
}

// --- Drawing a polygon (#2144): corners by clicks on free grid.
const pen = ref(null)
const penLine = computed(() => {
	if (!pen.value) return ""
	const points = pen.value.hover ? [...pen.value.points, pen.value.hover] : pen.value.points
	return points.map((p) => p.join(",")).join(" ")
})
const penCrosses = computed(() => Boolean(pen.value) && pen.value.points.length >= 3 && selfCrossing(pen.value.points))

function penClick(event) {
	const corner = cornerAt(event)
	if (!pen.value) {
		pen.value = { points: [corner], hover: corner }
		return
	}
	const [first] = pen.value.points
	const near = Math.hypot(corner[0] - first[0], corner[1] - first[1]) * props.tile <= EDGE_PX * 1.5
	if (near && pen.value.points.length >= 3) return finishPen()
	const last = pen.value.points[pen.value.points.length - 1]
	if (corner[0] === last[0] && corner[1] === last[1]) return
	if (pen.value.points.length >= MAX_POINTS) return
	pen.value.points.push(corner)
}

function finishPen() {
	const points = pen.value?.points || []
	if (points.length < 3 || selfCrossing(points)) return
	pen.value = null
	emit("draw", { shape: "Polygon", points, ...boxOf(points) })
}

function onKey(event) {
	if (!pen.value) return
	// Typing elsewhere (chat, a dialog field) keeps its own Backspace, Enter and Esc.
	if (event.target?.closest?.("input, textarea, select, [contenteditable='true'], [contenteditable='']")) return
	if (event.key === "Escape") pen.value = null
	else if (event.key === "Enter") finishPen()
	else if (event.key === "Backspace") {
		pen.value.points.pop()
		if (!pen.value.points.length) pen.value = null
	} else return
	event.preventDefault()
	event.stopPropagation()
}
watch(
	() => Boolean(pen.value),
	(on) => (on ? window.addEventListener("keydown", onKey, true) : window.removeEventListener("keydown", onKey, true))
)
watch(
	() => props.editing,
	(on) => !on && (pen.value = null)
)
onBeforeUnmount(() => window.removeEventListener("keydown", onKey, true))

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
	if (pen.value || !hit || hit.kind === "draw") return "crosshair"
	if (hit.kind === "move") return gesture.value ? "grabbing" : "grab"
	if (hit.kind === "point") return "move"
	if (hit.kind === "edge") return "copy"
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
		if (shapeOf(area) === "Polygon") {
			// A corner, an edge (adds a corner), or inside (moves it) (#2144).
			const points = pointsOf(area)
			const index = points.findIndex(([x, y]) => Math.hypot(x * t - px, y * t - py) <= EDGE_PX + 2)
			if (index >= 0) return { kind: "point", area, index }
			const edge = points.findIndex((p, i) => segmentDistance(p, points[(i + 1) % points.length], px / t, py / t) * t <= EDGE_PX)
			if (edge >= 0) return { kind: "edge", area, index: edge }
			if (contains(area, px / t, py / t)) return { kind: "move", area }
			continue
		}
		const left = area.x * t
		const top = area.y * t
		const right = left + area.width * t
		const bottom = top + area.height * t
		if (px < left - EDGE_PX || px > right + EDGE_PX || py < top - EDGE_PX || py > bottom + EDGE_PX) continue
		const edges =
			(Math.abs(py - top) <= EDGE_PX ? "n" : Math.abs(py - bottom) <= EDGE_PX ? "s" : "") +
			(Math.abs(px - left) <= EDGE_PX ? "w" : Math.abs(px - right) <= EDGE_PX ? "e" : "")
		if (edges) return { kind: "resize", area, edges }
		if (contains(area, px / t, py / t)) return { kind: "move", area }
	}
	return { kind: "draw" }
}

function snap(value) {
	return Math.round(value / STEP) * STEP
}

/** The area's new rectangle for a move or resize by (dx, dy) tiles, kept inside the grid. */
function reshape(g, dx, dy) {
	const a = g.area
	if (shapeOf(a) === "Polygon") return reshapePolygon(g, dx, dy)
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

/** A polygon moved, or one of its corners dragged (a new one when the drag started on an edge). */
function reshapePolygon(g, dx, dy) {
	const a = g.area
	let points = pointsOf(a).map((p) => [...p])
	if (g.kind === "move") {
		const box = boxOf(points)
		const mx = Math.max(-box.x, Math.min(props.cols - box.x - box.width, dx))
		const my = Math.max(-box.y, Math.min(props.rows - box.y - box.height, dy))
		points = points.map(([x, y]) => [x + mx, y + my])
	} else {
		const at = [
			Math.max(0, Math.min(props.cols, snap(g.corner[0] + dx))),
			Math.max(0, Math.min(props.rows, snap(g.corner[1] + dy))),
		]
		if (g.kind === "edge") points.splice(g.index + 1, 0, at)
		else points[g.index] = at
	}
	return { shape: "Polygon", points, ...boxOf(points) }
}

function onDown(event) {
	if (event.button !== 0) return
	const hit = pen.value ? { kind: "draw" } : hitAt(event)
	gesture.value = { ...hit, start: tileAt(event), corner: edgeCorner(hit, event) || cornerAt(event), clientX: event.clientX, clientY: event.clientY }
	try {
		// Keeps the drag when the pointer leaves the grid; some pointers can't be captured.
		layer.value.setPointerCapture(event.pointerId)
	} catch {
		// dragging still works while the pointer stays on the grid
	}
}

/** A new corner on a polygon's edge: the edge's point nearest the pointer, on the half-square grid. */
function edgeCorner(hit, event) {
	if (hit.kind !== "edge") return null
	const box = layer.value.getBoundingClientRect()
	const points = pointsOf(hit.area)
	const pointer = [(event.clientX - box.left) / props.tile, (event.clientY - box.top) / props.tile]
	const [x, y] = nearestOnSegment(points[hit.index], points[(hit.index + 1) % points.length], ...pointer)
	return [Math.max(0, Math.min(props.cols, snap(x))), Math.max(0, Math.min(props.rows, snap(y)))]
}

function onMove(event) {
	const g = gesture.value
	if (pen.value) {
		pen.value.hover = cornerAt(event)
		return
	}
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
		// A click without dragging: free grid sets a polygon corner; an edge gets a new corner;
		// a corner does nothing (a double-click removes it); else edit the area.
		if (g.kind === "draw") return penClick(g)  // a gesture carries clientX / clientY like an event
		if (g.kind === "edge") {
			const split = reshapePolygon(g, 0, 0)
			if (!selfCrossing(split.points)) emit("change", g.area, split)
			return
		}
		if (g.kind === "point") return
		if (g.area) emit("pick", g.area)
		return
	}
	if (g.kind === "draw") return emit("draw", rect)
	const a = g.area
	if (rect.shape === "Polygon") {
		if (selfCrossing(rect.points)) return
		if (JSON.stringify(rect.points) !== JSON.stringify(pointsOf(a))) emit("change", a, rect)
		return
	}
	if (rect.x !== a.x || rect.y !== a.y || rect.width !== a.width || rect.height !== a.height) emit("change", a, rect)
}

/** Double-click a polygon's corner: remove it (at least 3 stay). */
function onDoubleClick(event) {
	const hit = hitAt(event)
	if (hit.kind !== "point") return
	const points = pointsOf(hit.area)
	if (points.length <= 3) return
	points.splice(hit.index, 1)
	if (!selfCrossing(points)) emit("change", hit.area, { shape: "Polygon", points, ...boxOf(points) })
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
/* Shapes (#2144). An ellipse: the box rounded. A polygon: the box stays clear, the SVG draws it
   with the same fill and edge as a rectangle. */
.area--ellipse {
	border-radius: 50%;
}
.area--polygon {
	background: transparent;
	border-color: transparent;
	box-shadow: none;
	overflow: visible;
}
.area__shape {
	position: absolute;
	inset: 0;
	width: 100%;
	height: 100%;
	overflow: visible;
	pointer-events: none;
}
.area__shape polygon {
	fill: hsl(var(--area-h) 70% 42% / 0.32);
	stroke: hsl(var(--area-h) 70% 42% / 0.9);
	stroke-width: 2.5px;
	stroke-linejoin: round;
	filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.35));
}
.area--active .area__shape polygon {
	fill: hsl(var(--area-h) 70% 42% / 0.45);
	stroke: hsl(var(--area-h) 70% 35%);
}
.area--editing .area__shape polygon {
	stroke-dasharray: 6 4;
}
.area--start .area__shape polygon {
	fill: rgba(255, 255, 255, 0.4);
	stroke: rgba(255, 255, 255, 0.95);
	stroke-dasharray: 2 4;
}
.area--guests .area__shape polygon {
	stroke-width: 4px;
}
.area__handle--point {
	transform: translate(-50%, -50%);
	border-radius: 50%;
}
.area-pen__shape {
	fill: rgba(124, 58, 237, 0.35);
	stroke: rgb(109, 40, 217);
	stroke-width: 2.5px;
	stroke-dasharray: 6 4;
}
.area-pen__line {
	fill: none;
	stroke: rgb(109, 40, 217);
	stroke-width: 2.5px;
	stroke-dasharray: 6 4;
}
.area-pen__shape--bad,
.area-pen__line--bad {
	stroke: rgb(220, 38, 38);
}
.area-pen__corner {
	fill: #fff;
	stroke: rgb(109, 40, 217);
	stroke-width: 2px;
	vector-effect: non-scaling-stroke;
}
.area-pen__corner--close {
	fill: rgb(196, 181, 253);
}
.area-pen__hint {
	position: absolute;
	left: 50%;
	top: 8px;
	transform: translateX(-50%);
	z-index: 40;
	white-space: nowrap;
	border-radius: 6px;
	background: rgba(15, 23, 42, 0.85);
	color: #fff;
	font-size: 12px;
	padding: 3px 8px;
	pointer-events: none;
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
