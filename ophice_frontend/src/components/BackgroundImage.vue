<template>
	<!--
		Ophice's background image, placed in grid tiles (#2089). It is the world (#2139): its edges
		fade out softly, so the map ends like a horizon, not a cut. With `frame` (edit mode "Adjust") it is only the outline with
		handles: drag inside to move it, drag a corner to resize it (half-tile steps, Alt = free).
	-->
	<div v-if="!frame" class="bg-image pointer-events-none absolute select-none" :style="box" aria-hidden="true">
		<img :src="src" alt="" draggable="false" class="h-full w-full max-w-none" data-testid="background-image" />
		<div class="bg-image__shade absolute inset-0" />
	</div>
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
/* Soft edges of the map (#2139), like the cockpit glow: the image darkens towards its edges in
   a gentle fade and then fades out, so the map ends like a horizon, not a cut. */
.bg-image {
	--fade-out: 3%;
	--shade: rgb(15 23 42 / 0.55);
	--shade-in: 9%;
	-webkit-mask-image: linear-gradient(to right, transparent, #000 var(--fade-out), #000 calc(100% - var(--fade-out)), transparent),
		linear-gradient(to bottom, transparent, #000 var(--fade-out), #000 calc(100% - var(--fade-out)), transparent);
	-webkit-mask-composite: source-in;
	mask-image: linear-gradient(to right, transparent, #000 var(--fade-out), #000 calc(100% - var(--fade-out)), transparent),
		linear-gradient(to bottom, transparent, #000 var(--fade-out), #000 calc(100% - var(--fade-out)), transparent);
	mask-composite: intersect;
}
.bg-image__shade {
	background:
		linear-gradient(to right, var(--shade), transparent var(--shade-in)),
		linear-gradient(to left, var(--shade), transparent var(--shade-in)),
		linear-gradient(to bottom, var(--shade), transparent var(--shade-in)),
		linear-gradient(to top, var(--shade), transparent var(--shade-in));
}
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
