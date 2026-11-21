<template>
	<!-- Date header of the Roadmap (#2034): two rows per zoom and the today line.
	     week: months over calendar weeks; month: quarters over months; quarter: quarters over months. -->
	<div class="roadmap-header" :style="{ width: `${timeline.totalWidth}px` }">
		<div v-if="today" class="hr-gantt-today-strip" :style="{ left: `${today.left}px`, width: `${today.width}px` }" />
		<div v-if="today" class="hr-gantt-today-strip-edge" :style="{ left: `${today.edgeLeft}px` }" :title="__('Today')" />
		<div v-for="(row, idx) in headerRows" :key="idx" class="roadmap-header__row">
			<div
				v-for="segment in row"
				:key="segment.key"
				class="roadmap-header__cell"
				:style="{ left: `${segment.left}px`, width: `${segment.width}px` }"
				:title="segment.title || segment.label"
			>
				{{ segment.label }}
			</div>
		</div>
	</div>
</template>

<script setup>
import { computed } from "vue"
import { __ } from "@spa/utils/i18n.js"
import { userLocale } from "@spa/utils/datetime.js"
import { quarterSegments, toDay } from "@spa/utils/roadmapLayout.js"

const props = defineProps({
	/** from roadmapTimeline / buildTimeline */
	timeline: { type: Object, required: true },
	zoom: { type: String, default: "month" },
	/** todayStripRect(timeline), or null when today is outside the range */
	today: { type: Object, default: null },
})

function quarterRow(withYear) {
	return quarterSegments(props.timeline).map((q) => ({
		key: q.key,
		left: q.left,
		width: q.width,
		label: withYear ? __("Q{0} {1}", [q.quarter, q.year]) : __("Q{0}", [q.quarter]),
		title: __("Q{0} {1}", [q.quarter, q.year]),
	}))
}

function monthRow(short) {
	const fmt = short ? new Intl.DateTimeFormat(userLocale(), { month: "short" }) : null
	return props.timeline.months.map((m) => ({
		key: m.key,
		left: m.left,
		width: m.width,
		label: short ? fmt.format(toDay(m.startIso)) : m.label,
		title: m.label,
	}))
}

const headerRows = computed(() => {
	if (props.zoom === "week") {
		const weeks = props.timeline.weeks.map((w) => ({
			key: w.key,
			left: w.left,
			width: w.width,
			label: __("W{0}", [w.number]),
		}))
		return [monthRow(false), weeks]
	}
	if (props.zoom === "quarter") return [quarterRow(true), monthRow(true)]
	return [quarterRow(true), monthRow(false)]
})
</script>

<style scoped>
.roadmap-header {
	position: relative;
	height: 40px;
}

.roadmap-header__row {
	position: relative;
	height: 20px;
	border-bottom: 1px solid var(--outline-gray-2);
}

.roadmap-header__cell {
	position: absolute;
	top: 0;
	height: 100%;
	overflow: hidden;
	padding: 0 4px;
	border-left: 1px solid var(--outline-gray-2);
	color: var(--ink-gray-6);
	font-size: 11px;
	line-height: 19px;
	text-overflow: ellipsis;
	white-space: nowrap;
	z-index: 2;
}
</style>
