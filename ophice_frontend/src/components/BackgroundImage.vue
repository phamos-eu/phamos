<template>
	<!--
		Ophice's background image, placed in grid tiles (#2089). It is the world (#2139): its edges
		fade out softly, so the map ends like a horizon, not a cut. With `frame` (edit mode "Adjust") it is only the outline with
		handles: drag inside to move it, drag a corner to resize it (half-tile steps, Alt = free).
	-->
	<div v-if="!frame" class="bg-image pointer-events-none absolute select-none" :style="[box, edgeVars]" aria-hidden="true">
		<img :src="src" alt="" draggable="false" class="bg-image__img h-full w-full max-w-none" data-testid="background-image" />
		<div class="bg-image__shade absolute inset-0" />
		<div class="bg-image__tide absolute inset-0" :style="phase('tide')" />
		<i v-for="side in SIDES" :key="side" class="bg-image__edge" :class="`bg-image__edge--${side}`">
			<i class="bg-image__wave" :style="phase(`${side}-a`)"><i class="bg-image__wave-b" :style="phase(`${side}-b`)" /></i>
		</i>
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

// The map's edge (#2139): rounded, darker towards the rim, moving like a slow tide. Sizes follow
// the image's size on screen.
const SIDES = ["top", "right", "bottom", "left"]
const edgeVars = computed(() => {
	const short = Math.min(props.placement.width, props.placement.height) * props.tile
	return { "--edge": `${Math.round(short * 0.07)}px`, "--round": `${Math.round(short * 0.05)}px` }
})

// Wave speeds in seconds: primes, so the waves never line up the same way again (they would after
// the product of all of them: millions of years). Each one starts where the clock says it is, so a
// reload continues the motion and everyone sees the same sea.
const PERIODS = {
	tide: 53,
	"top-a": 23,
	"top-b": 37,
	"right-a": 29,
	"right-b": 41,
	"bottom-a": 31,
	"bottom-b": 43,
	"left-a": 19,
	"left-b": 47,
}
const now = Date.now() / 1000
function phase(key) {
	const period = PERIODS[key]
	return { animationDuration: `${period}s`, animationDelay: `${-(now % period).toFixed(2)}s` }
}

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
/* Soft, rounded edges of the map (#2139), like the cockpit glow: the image darkens towards its
   rim and fades out, so the map ends like a horizon, not a cut. A slow tide breathes in and out and
   faint waves run along each side, clockwise. Only transform and opacity move (the compositor);
   no script runs per frame. */
.bg-image {
	--fade-out: 2.5%;
	--shade: rgb(15 23 42 / 0.42);
	border-radius: var(--round);
}
/* The fade-out sits on the still image only: a mask on the parent would make the browser
   recomposite the whole image for every frame of the waves. */
.bg-image__img {
	border-radius: inherit;
	-webkit-mask-image: linear-gradient(to right, transparent, #000 var(--fade-out), #000 calc(100% - var(--fade-out)), transparent),
		linear-gradient(to bottom, transparent, #000 var(--fade-out), #000 calc(100% - var(--fade-out)), transparent);
	-webkit-mask-composite: source-in;
	mask-image: linear-gradient(to right, transparent, #000 var(--fade-out), #000 calc(100% - var(--fade-out)), transparent),
		linear-gradient(to bottom, transparent, #000 var(--fade-out), #000 calc(100% - var(--fade-out)), transparent);
	mask-composite: intersect;
}
/* The rim: an inset shadow follows the rounded corners. */
.bg-image__shade,
.bg-image__tide {
	border-radius: inherit;
	box-shadow: inset 0 0 var(--edge) calc(var(--edge) * 0.35) var(--shade);
}
/* The tide: a second rim that grows a little and fades, so the dark edge breathes in and out. */
.bg-image__tide {
	--shade: rgb(15 23 42 / 0.22);
	will-change: transform, opacity;
	animation: bg-image-tide linear infinite;
}
@keyframes bg-image-tide {
	0%, 100% { opacity: 1; transform: scale(1); animation-timing-function: ease-in-out; }
	50% { opacity: 0.35; transform: scale(1.012); animation-timing-function: ease-in-out; }
}
/* Waves along each side (as .cockpit-glow__wave): a dark band fading inwards, its strength
   modulated by two repeating masks of different lengths that slide along the side. */
.bg-image__edge {
	position: absolute;
	overflow: hidden;
	--wave-a: 360px;
	--wave-b: 610px;
	--band: rgb(15 23 42 / 0.28);
}
.bg-image__edge--top,
.bg-image__edge--bottom {
	left: 0;
	right: 0;
	height: var(--edge);
	-webkit-mask-image: linear-gradient(to right, transparent, #000 var(--round), #000 calc(100% - var(--round)), transparent);
	mask-image: linear-gradient(to right, transparent, #000 var(--round), #000 calc(100% - var(--round)), transparent);
}
.bg-image__edge--left,
.bg-image__edge--right {
	top: 0;
	bottom: 0;
	width: var(--edge);
	-webkit-mask-image: linear-gradient(to bottom, transparent, #000 var(--round), #000 calc(100% - var(--round)), transparent);
	mask-image: linear-gradient(to bottom, transparent, #000 var(--round), #000 calc(100% - var(--round)), transparent);
}
.bg-image__edge--top { top: 0; }
.bg-image__edge--bottom { bottom: 0; }
.bg-image__edge--left { left: 0; }
.bg-image__edge--right { right: 0; }
.bg-image__wave,
.bg-image__wave-b {
	position: absolute;
	top: 0;
	left: 0;
	will-change: transform;
	-webkit-mask-image: var(--wave);
	mask-image: var(--wave);
	animation-timing-function: linear;
	animation-iteration-count: infinite;
}
.bg-image__edge--top .bg-image__wave,
.bg-image__edge--bottom .bg-image__wave {
	width: calc(100% + var(--wave-a));
	height: 100%;
	--wave: repeating-linear-gradient(to right, #000 0, rgb(0 0 0 / 0.25) calc(var(--wave-a) / 2), #000 var(--wave-a));
	animation-name: bg-image-wave-a-x;
}
.bg-image__edge--top .bg-image__wave-b,
.bg-image__edge--bottom .bg-image__wave-b {
	width: calc(100% + var(--wave-b));
	height: 100%;
	--wave: repeating-linear-gradient(to right, #000 0, rgb(0 0 0 / 0.4) calc(var(--wave-b) / 2), #000 var(--wave-b));
	animation-name: bg-image-wave-b-x;
}
.bg-image__edge--left .bg-image__wave,
.bg-image__edge--right .bg-image__wave {
	width: 100%;
	height: calc(100% + var(--wave-a));
	--wave: repeating-linear-gradient(to bottom, #000 0, rgb(0 0 0 / 0.25) calc(var(--wave-a) / 2), #000 var(--wave-a));
	animation-name: bg-image-wave-a-y;
}
.bg-image__edge--left .bg-image__wave-b,
.bg-image__edge--right .bg-image__wave-b {
	width: 100%;
	height: calc(100% + var(--wave-b));
	--wave: repeating-linear-gradient(to bottom, #000 0, rgb(0 0 0 / 0.4) calc(var(--wave-b) / 2), #000 var(--wave-b));
	animation-name: bg-image-wave-b-y;
}
/* The band itself, dark at the rim, clear inwards (wave B carries it). */
.bg-image__edge--top .bg-image__wave-b { background: linear-gradient(to bottom, var(--band), transparent); }
.bg-image__edge--bottom .bg-image__wave-b { background: linear-gradient(to top, var(--band), transparent); }
.bg-image__edge--left .bg-image__wave-b { background: linear-gradient(to right, var(--band), transparent); }
.bg-image__edge--right .bg-image__wave-b { background: linear-gradient(to left, var(--band), transparent); }
/* Clockwise: right along the top, down the right, left along the bottom, up the left. */
.bg-image__edge--bottom .bg-image__wave,
.bg-image__edge--bottom .bg-image__wave-b,
.bg-image__edge--left .bg-image__wave,
.bg-image__edge--left .bg-image__wave-b {
	animation-direction: reverse;
}
@keyframes bg-image-wave-a-x {
	from { transform: translateX(calc(-1 * var(--wave-a))); }
	to { transform: translateX(0); }
}
@keyframes bg-image-wave-b-x {
	from { transform: translateX(calc(-1 * var(--wave-b))); }
	to { transform: translateX(0); }
}
@keyframes bg-image-wave-a-y {
	from { transform: translateY(calc(-1 * var(--wave-a))); }
	to { transform: translateY(0); }
}
@keyframes bg-image-wave-b-y {
	from { transform: translateY(calc(-1 * var(--wave-b))); }
	to { transform: translateY(0); }
}
/* !important: the edge rules that set the wave animations are more specific than these. */
@media (prefers-reduced-motion: reduce) {
	.bg-image__tide,
	.bg-image__wave,
	.bg-image__wave-b {
		animation: none !important;
	}
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
