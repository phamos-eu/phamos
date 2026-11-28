<template>
	<!-- Where the bar sat in the baseline (#2034): a thin grey bar under the plan bar. -->
	<div
		class="roadmap-baseline-bar"
		:style="{ left: `${rect.left}px`, top: `${rect.top}px`, width: `${rect.width}px` }"
		:title="title"
		role="img"
		:aria-label="title"
	/>
</template>

<script setup>
import { computed } from "vue"
import { __ } from "@spa/utils/i18n.js"
import { formatDate } from "@spa/utils/datetime.js"
import { isoDay } from "@spa/utils/roadmapLayout.js"

const props = defineProps({
	/** { start, end } of the baseline */
	baseline: { type: Object, required: true },
	/** { left, top, width } in px */
	rect: { type: Object, required: true },
})

const title = computed(() =>
	__("Baseline: {0} – {1}", [formatDate(isoDay(props.baseline.start)), formatDate(isoDay(props.baseline.end))])
)
</script>

<style scoped>
.roadmap-baseline-bar {
	position: absolute;
	height: 3px;
	border-radius: 2px;
	background: var(--ink-gray-4);
	opacity: 0.7;
}
</style>
