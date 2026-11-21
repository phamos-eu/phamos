<template>
	<!-- Next to a bar's end (#2034): the shift against the baseline ("+5 d") and the slack from
	     the server ("2 d slack", or "3 d late" when negative). Nothing when both are empty or 0. -->
	<span
		v-if="shiftText || slackText"
		class="roadmap-slack"
		:class="{ 'roadmap-slack--inside': inside }"
		:style="{ left: `${left}px`, top: `${top}px` }"
	>
		<span v-if="shiftText" class="roadmap-slack__shift" :title="__('Against the baseline')">{{ shiftText }}</span>
		<span v-if="slackText" :class="slackDays < 0 ? 'roadmap-slack__late' : 'roadmap-slack__slack'">{{ slackText }}</span>
	</span>
</template>

<script setup>
import { computed } from "vue"
import { __ } from "@spa/utils/i18n.js"

const props = defineProps({
	slackDays: { type: Number, default: null },
	shiftDays: { type: Number, default: null },
	/** px of the vertical centre, and of the left edge (or of the right edge when `inside`) */
	left: { type: Number, required: true },
	top: { type: Number, required: true },
	/** inside the bar's right end, when the next bar follows too closely for room after it */
	inside: { type: Boolean, default: false },
})

const shiftText = computed(() => {
	const days = props.shiftDays
	if (!days) return ""
	return days > 0 ? __("+{0} d", [days]) : __("{0} d", [days])
})

const slackText = computed(() => {
	const days = props.slackDays
	if (!days) return ""
	return days < 0 ? __("{0} d late", [-days]) : __("{0} d slack", [days])
})
</script>

<style scoped>
.roadmap-slack {
	position: absolute;
	display: flex;
	gap: 4px;
	transform: translateY(-50%);
	font-size: 10px;
	line-height: 1;
	white-space: nowrap;
	pointer-events: none;
}

.roadmap-slack--inside {
	z-index: 4;
	transform: translate(-100%, -50%);
	border-radius: 3px;
	padding: 1px 2px;
	background: var(--surface-white);
}

.roadmap-slack__shift {
	color: var(--ink-amber-3);
	font-weight: 600;
	pointer-events: auto;
}

.roadmap-slack__slack {
	color: var(--ink-gray-5);
}

.roadmap-slack__late {
	color: var(--ink-red-3);
	font-weight: 600;
}
</style>
