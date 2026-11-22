<template>
	<!--
		Dims the map outside the walkable part (#2089): the background image may reach beyond the grid;
		those parts stay visible by panning, but darker and a little blurred. Takes the revealed
		rectangle as a prop, so the per-user fog of war (#2090) can later pass explored tiles instead.
	-->
	<div class="pointer-events-none absolute inset-0" aria-hidden="true" data-testid="map-fog">
		<div v-for="(part, index) in parts" :key="index" class="map-fog__part absolute" :style="part" />
		<div class="map-fog__edge absolute" :style="edgeStyle" />
	</div>
</template>

<script setup>
import { computed } from "vue"

const props = defineProps({
	/** The whole map in tiles: { x, y, w, h } (the grid and the image together) */
	canvas: { type: Object, required: true },
	/** What stays clear, in grid tiles: { x, y, w, h } (now: the walkable grid) */
	revealed: { type: Object, required: true },
	tile: { type: Number, required: true },
})

const px = (tiles) => `${tiles * props.tile}px`

// Four bands around the revealed rectangle, in canvas px.
const parts = computed(() => {
	const c = props.canvas
	const r = props.revealed
	const left = r.x - c.x
	const top = r.y - c.y
	const right = c.w - left - r.w
	const bottom = c.h - top - r.h
	const bands = [
		{ left: 0, top: 0, width: c.w, height: top },
		{ left: 0, top: top + r.h, width: c.w, height: bottom },
		{ left: 0, top, width: left, height: r.h },
		{ left: left + r.w, top, width: right, height: r.h },
	]
	return bands
		.filter((b) => b.width > 0.001 && b.height > 0.001)
		.map((b) => ({ left: px(b.left), top: px(b.top), width: px(b.width), height: px(b.height) }))
})

// A soft inner shadow along the revealed edge, so the border reads as a horizon, not a cut.
const edgeStyle = computed(() => ({
	left: px(props.revealed.x - props.canvas.x),
	top: px(props.revealed.y - props.canvas.y),
	width: px(props.revealed.w),
	height: px(props.revealed.h),
}))
</script>

<style scoped>
.map-fog__part {
	background: rgba(15, 23, 42, 0.5);
	backdrop-filter: blur(2px) grayscale(0.4);
	-webkit-backdrop-filter: blur(2px) grayscale(0.4);
}
.map-fog__edge {
	box-shadow: 0 0 18px 6px rgba(15, 23, 42, 0.35);
	border-radius: 2px;
}
</style>
