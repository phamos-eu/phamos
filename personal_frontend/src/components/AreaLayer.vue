<template>
	<!--
		Meeting areas (#2060): lightly tinted rectangles with their name and the Jitsi watermark.
		In edit mode a layer over the grid takes the pointer: drag to draw, click an area to edit.
	-->
	<div class="pointer-events-none absolute inset-0">
		<div
			v-for="area in areas"
			:key="area.name"
			class="area absolute flex flex-col items-center justify-center overflow-hidden rounded-md"
			:class="{ 'area--active': area.name === activeName, 'area--editing': editing }"
			:style="{ ...rectStyle(area), '--area-h': area.color_hue ?? 265 }"
			:title="area.title"
			data-testid="meeting-area"
		>
			<img
				v-if="!failedLogos[area.jitsi_domain]"
				:src="`https://${area.jitsi_domain}/images/watermark.svg`"
				alt=""
				class="area__logo"
				draggable="false"
				@error="failedLogos[area.jitsi_domain] = true"
			/>
			<span v-else class="area__logo-text">Jitsi</span>
			<span class="area__title truncate">{{ area.title }}</span>
		</div>

		<div v-if="draft" class="area area--draft absolute rounded-md" :style="rectStyle(draft)" />

		<div
			v-if="editing"
			ref="layer"
			class="pointer-events-auto absolute inset-0 cursor-crosshair"
			data-testid="area-edit-layer"
			@pointerdown="onDown"
			@pointermove="onMove"
			@pointerup="onUp"
			@pointercancel="draft = null"
		/>
	</div>
</template>

<script setup>
import { reactive, ref } from "vue"

const props = defineProps({
	areas: { type: Array, default: () => [] },
	tile: { type: Number, required: true },
	cols: { type: Number, required: true },
	rows: { type: Number, required: true },
	editing: { type: Boolean, default: false },
	/** The area whose meeting I am in */
	activeName: { type: String, default: "" },
})
const emit = defineEmits(["draw", "pick"])

const layer = ref(null)
const draft = ref(null)
const failedLogos = reactive({})
let start = null

function rectStyle(rect) {
	const t = props.tile
	return {
		left: `${rect.x * t}px`,
		top: `${rect.y * t}px`,
		width: `${rect.width * t}px`,
		height: `${rect.height * t}px`,
	}
}

function tileAt(event) {
	const box = layer.value.getBoundingClientRect()
	const x = Math.floor((event.clientX - box.left) / props.tile)
	const y = Math.floor((event.clientY - box.top) / props.tile)
	return { x: Math.max(0, Math.min(props.cols - 1, x)), y: Math.max(0, Math.min(props.rows - 1, y)) }
}

function rectBetween(a, b) {
	const x = Math.min(a.x, b.x)
	const y = Math.min(a.y, b.y)
	return { x, y, width: Math.abs(a.x - b.x) + 1, height: Math.abs(a.y - b.y) + 1 }
}

function onDown(event) {
	if (event.button !== 0) return
	start = { ...tileAt(event), clientX: event.clientX, clientY: event.clientY }
	try {
		// Keeps the drag when the pointer leaves the grid; some pointers can't be captured.
		layer.value.setPointerCapture(event.pointerId)
	} catch {
		// drawing still works while the pointer stays on the grid
	}
}

function onMove(event) {
	if (!start) return
	const moved = Math.hypot(event.clientX - start.clientX, event.clientY - start.clientY)
	if (moved < 4 && !draft.value) return
	draft.value = rectBetween(start, tileAt(event))
}

function onUp(event) {
	if (!start) return
	const rect = draft.value
	const down = start
	start = null
	draft.value = null
	if (rect) return emit("draw", rect)
	// A click without dragging: edit the area under the pointer, if any.
	const area = props.areas.find(
		(a) => down.x >= a.x && down.x < a.x + a.width && down.y >= a.y && down.y < a.y + a.height
	)
	if (area) emit("pick", area)
}
</script>

<style scoped>
/* Clearly visible on any map (PM: "a little more solid"), each area in its own random color
   (--area-h, a hue; PM 2026-11-22): a solid tint, a firm edge with a light inner line, and
   the white Jitsi watermark with a dark halo. Saturation and lightness stay fixed so the
   title and logo read the same on every color. */
.area {
	--area-h: 265;
	background: hsl(var(--area-h) 75% 50% / 0.3);
	border: 2.5px solid hsl(var(--area-h) 70% 42% / 0.9);
	box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.6), 0 1px 4px rgba(0, 0, 0, 0.35);
	color: #fff;
	gap: 3px;
}
.area--active {
	background: hsl(var(--area-h) 75% 50% / 0.42);
	border-color: hsl(var(--area-h) 70% 35%);
}
.area--editing {
	border-style: dashed;
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
