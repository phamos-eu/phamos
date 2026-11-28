<template>
	<!--
		Ophice's background image, placed in grid tiles (#2089). It may reach beyond the grid (those
		parts are dimmed by MapFog). With `frame` (edit mode "Adjust") it is only the outline with
		handles: drag inside to move it, drag a corner to resize it (half-tile steps, Alt = free).
	-->
	<img
		v-if="!frame"
		:src="src"
		alt=""
		draggable="false"
		class="pointer-events-none absolute max-w-none select-none"
		:style="box"
		data-testid="background-image"
	/>
	<div
		v-else
		class="bg-frame absolute"
		:class="{ 'bg-frame--busy': gesture }"
		:style="box"
		data-testid="background-frame"
		@pointerdown.stop="start('move', $event)"
		@pointermove="move"
		@pointerup="end"
		@pointercancel="end"
	>
		<span
			v-for="corner in CORNERS"
			:key="corner"
			class="bg-frame__handle"
			:class="`bg-frame__handle--${corner}`"
			:title="__('Drag to resize (Alt: without snapping)')"
			:data-testid="`background-resize-${corner}`"
			@pointerdown.stop="start(corner, $event)"
		/>
		<span class="bg-frame__size">{{ sizeLabel }}</span>
	</div>
</template>

<script setup>
import { computed, ref } from "vue"
import { __ } from "@spa/utils/i18n.js"
import { snapHalf } from "../utils/ophiceView.js"

const props = defineProps({
	src: { type: String, required: true },
	/** Where the image lies, in grid tiles: { left, top, width, height } */
	placement: { type: Object, required: true },
	/** The whole map in tiles: { x, y } is where the canvas starts */
	canvas: { type: Object, required: true },
	tile: { type: Number, required: true },
	/** width / height */
	ratio: { type: Number, default: 0 },
	/** Edit mode: the outline with move and resize handles instead of the image */
	frame: { type: Boolean, default: false },
})
const emit = defineEmits(["change"])

const CORNERS = ["nw", "ne", "sw", "se"]
const MIN_WIDTH = 5

const box = computed(() => ({
	left: `${(props.placement.left - props.canvas.x) * props.tile}px`,
	top: `${(props.placement.top - props.canvas.y) * props.tile}px`,
	width: `${props.placement.width * props.tile}px`,
	height: `${props.placement.height * props.tile}px`,
}))

const sizeLabel = computed(() => __("{0} × {1} tiles", [fmt(props.placement.width), fmt(props.placement.height)]))
function fmt(value) {
	return Math.round(value * 10) / 10
}

const gesture = ref(null)

function start(kind, event) {
	if (event.button !== 0) return
	gesture.value = { kind, x: event.clientX, y: event.clientY, from: { ...props.placement } }
	try {
		event.currentTarget.setPointerCapture(event.pointerId)
	} catch {
		// still works while the pointer stays on the frame
	}
}

function move(event) {
	const g = gesture.value
	if (!g || !props.tile) return
	const dx = (event.clientX - g.x) / props.tile
	const dy = (event.clientY - g.y) / props.tile
	const from = g.from
	const ratio = props.ratio > 0 ? props.ratio : from.width / from.height
	if (g.kind === "move") {
		emit("change", { left: round(from.left + dx), top: round(from.top + dy), width: from.width })
		return
	}
	// Resize from a corner, keeping the ratio; the opposite corner stays where it is.
	const grows = g.kind.includes("e") ? dx : -dx
	let width = Math.max(MIN_WIDTH, from.width + grows)
	if (!event.altKey) width = Math.max(MIN_WIDTH, snapHalf(width))
	const height = width / ratio
	const left = g.kind.includes("w") ? from.left + from.width - width : from.left
	const top = g.kind.includes("n") ? from.top + from.height - height : from.top
	emit("change", { left: round(left), top: round(top), width: round(width) })
}

function end() {
	gesture.value = null
}

function round(value) {
	return Math.round(value * 1000) / 1000
}
</script>

<style scoped>
.bg-frame {
	z-index: 40;
	cursor: grab;
	outline: 2px dashed rgba(124, 58, 237, 0.95);
	outline-offset: -1px;
	background: rgba(124, 58, 237, 0.06);
	touch-action: none;
}
.bg-frame--busy {
	cursor: grabbing;
}
.bg-frame__handle {
	position: absolute;
	width: 14px;
	height: 14px;
	border-radius: 3px;
	background: #fff;
	border: 2px solid rgb(109, 40, 217);
	box-shadow: 0 1px 3px rgba(0, 0, 0, 0.4);
}
.bg-frame__handle--nw {
	left: -7px;
	top: -7px;
	cursor: nwse-resize;
}
.bg-frame__handle--ne {
	right: -7px;
	top: -7px;
	cursor: nesw-resize;
}
.bg-frame__handle--sw {
	left: -7px;
	bottom: -7px;
	cursor: nesw-resize;
}
.bg-frame__handle--se {
	right: -7px;
	bottom: -7px;
	cursor: nwse-resize;
}
.bg-frame__size {
	position: absolute;
	left: 8px;
	top: 8px;
	padding: 1px 6px;
	border-radius: 4px;
	background: rgba(76, 29, 149, 0.85);
	color: #fff;
	font-size: 11px;
	pointer-events: none;
}
</style>
