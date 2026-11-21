<template>
	<!-- Markers (#2034): GitLab milestones and releases as diamonds in the strip at the top,
	     with a thin line down through the rows. The tooltip names the marker and its date. -->
	<div class="roadmap-markers" :style="{ height: `${height}px` }">
		<div
			v-for="marker in placed"
			:key="marker.key"
			class="roadmap-marker"
			:class="`roadmap-marker--${marker.type}`"
			:style="{ left: `${marker.x}px` }"
		>
			<span class="roadmap-marker__line" />
			<span class="roadmap-marker__diamond" role="img" :aria-label="marker.title" :title="marker.title" />
		</div>
	</div>
</template>

<script setup>
import { computed } from "vue"
import { __ } from "@spa/utils/i18n.js"
import { formatDate } from "@spa/utils/datetime.js"
import { dateToX, isoDay } from "@spa/utils/roadmapLayout.js"

const props = defineProps({
	/** [{ name, type: "milestone" | "release", title, date }] */
	markers: { type: Array, default: () => [] },
	timeline: { type: Object, required: true },
	/** full height of the rows below, so the lines reach the bottom */
	height: { type: Number, required: true },
})

const TYPE_LABEL = {
	milestone: () => __("GitLab milestone"),
	release: () => __("Release"),
}

const placed = computed(() => {
	const columnWidth = props.timeline.days?.[0]?.width || 0
	const out = []
	for (const marker of props.markers || []) {
		const x = dateToX(props.timeline, marker.date)
		if (x === null || x < 0 || x >= props.timeline.totalWidth) continue
		const type = marker.type === "release" ? "release" : "milestone"
		out.push({
			key: `${type}:${marker.name}`,
			type,
			x: x + columnWidth / 2,
			title: `${TYPE_LABEL[type]()}: ${marker.title || marker.name} · ${formatDate(isoDay(marker.date))}`,
		})
	}
	return out
})
</script>

<style scoped>
.roadmap-markers {
	position: absolute;
	top: 0;
	left: 0;
	width: 100%;
	pointer-events: none;
	z-index: 2;
}

.roadmap-marker {
	position: absolute;
	top: 0;
	bottom: 0;
	--marker-color: var(--ink-violet-1);
}

.roadmap-marker--release {
	--marker-color: var(--ink-green-3);
}

.roadmap-marker__line {
	position: absolute;
	top: 6px;
	bottom: 0;
	left: -0.5px;
	border-left: 1px dashed var(--marker-color);
	opacity: 0.6;
}

.roadmap-marker__diamond {
	position: absolute;
	top: 1px;
	left: -5px;
	width: 10px;
	height: 10px;
	transform: rotate(45deg);
	border: 1px solid var(--surface-white);
	background: var(--marker-color);
	pointer-events: auto;
	cursor: default;
}
</style>
