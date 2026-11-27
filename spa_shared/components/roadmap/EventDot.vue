<template>
	<!-- A feature event (#2034): ○ planned, ● finished. Dots that would overlap come as one
	     stack with their count; "mixed" when some of them are finished. -->
	<div
		role="button"
		tabindex="0"
		class="roadmap-event"
		:class="[
			`roadmap-event--${stack.status}`,
			{ 'roadmap-event--stack': stack.count > 1, 'roadmap-event--selected': selected },
		]"
		:style="{ left: `${stack.x}px`, top: `${top}px` }"
		:aria-pressed="selected ? 'true' : 'false'"
		:aria-label="title"
		:title="title"
	>
		<span v-if="stack.count > 1" class="roadmap-event__count">{{ stack.count }}</span>
	</div>
</template>

<script setup>
import { computed } from "vue"
import { __ } from "@spa/utils/i18n.js"
import { formatDate } from "@spa/utils/datetime.js"
import { isoDay } from "@spa/utils/roadmapLayout.js"

const props = defineProps({
	/** a stack from stackEvents: { name, x, count, status, events: [{ name, label, date, status }] } */
	stack: { type: Object, required: true },
	/** vertical centre of the dot in px */
	top: { type: Number, required: true },
	selected: { type: Boolean, default: false },
})

const title = computed(() =>
	props.stack.events
		.map((e) => `${e.label || e.name} · ${e.status === "finished" ? __("finished") : __("planned")} · ${formatDate(isoDay(e.date))}`)
		.join("\n")
)
</script>

<style scoped>
.roadmap-event {
	position: absolute;
	display: flex;
	height: 10px;
	min-width: 10px;
	align-items: center;
	justify-content: center;
	transform: translate(-50%, -50%);
	border: 1.5px solid var(--ink-blue-3);
	border-radius: 9999px;
	background: var(--surface-white);
	cursor: pointer;
}

.roadmap-event--finished {
	background: var(--ink-blue-3);
}

.roadmap-event--mixed {
	background: linear-gradient(90deg, var(--ink-blue-3) 50%, var(--surface-white) 50%);
}

.roadmap-event--stack {
	height: 13px;
	min-width: 16px;
	padding: 0 3px;
}

.roadmap-event__count {
	border-radius: 9999px;
	padding: 0 2px;
	background: var(--surface-white);
	color: var(--ink-gray-8);
	font-size: 9px;
	font-weight: 600;
	line-height: 1;
}

.roadmap-event:hover {
	border-color: var(--ink-blue-4);
}

.roadmap-event--selected,
.roadmap-event:focus-visible {
	outline: 2px solid var(--ink-blue-3);
	outline-offset: 2px;
}
</style>
