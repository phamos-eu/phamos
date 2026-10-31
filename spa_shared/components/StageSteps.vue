<template>
	<!-- Chevron step bar (#1773), the cockpit twin of the ticket order's step bar on the event page. -->
	<ol
		class="stage-steps flex w-full list-none p-0"
		:class="[size === 'compact' ? 'stage-steps--compact' : 'stage-steps--full', dimmed ? 'opacity-50' : '']"
		:title="size === 'compact' ? tooltip : undefined"
		:aria-label="ariaLabel || tooltip"
	>
		<li
			v-for="(step, index) in steps"
			:key="step.value"
			class="stage-step relative flex min-w-0 flex-1 items-center justify-center"
			:class="stateClass(index)"
			:aria-current="stepState(index, currentIndex) === 'current' ? 'step' : undefined"
		>
			<button
				v-if="size === 'full' && clickable"
				type="button"
				class="flex h-full w-full min-w-0 items-center justify-center gap-1.5 px-1 focus:outline-none focus-visible:underline"
				:title="step.hint || step.label"
				@click="emit('select', step.value)"
			>
				<span class="stage-step-no">{{ stepState(index, currentIndex) === "done" ? "✓" : index + 1 }}</span>
				<span class="truncate">{{ step.label }}</span>
			</button>
			<span v-else-if="size === 'full'" class="flex min-w-0 items-center justify-center gap-1.5 px-1" :title="step.hint || step.label">
				<span class="stage-step-no">{{ stepState(index, currentIndex) === "done" ? "✓" : index + 1 }}</span>
				<span class="truncate">{{ step.label }}</span>
			</span>
		</li>
	</ol>
</template>

<script setup>
import { computed } from "vue"
import { __ } from "@spa/utils/i18n.js"
import { progress, stepIndex, stepState } from "@spa/utils/stageSteps.js"

const props = defineProps({
	/** [{ value, label, hint? }] in order */
	steps: { type: Array, required: true },
	/** value of the current step; a value off the path shows nothing done */
	current: { type: String, default: "" },
	/** "full": numbered chevrons with labels; "compact": a thin bar with a tooltip */
	size: { type: String, default: "full" },
	clickable: { type: Boolean, default: false },
	dimmed: { type: Boolean, default: false },
	ariaLabel: { type: String, default: "" },
})
const emit = defineEmits(["select"])

const currentIndex = computed(() => stepIndex(props.steps, props.current))
const tooltip = computed(() => {
	const p = progress(props.steps, props.current)
	return p ? __("{0}, step {1} of {2}", [p.label, p.step, p.total]) : props.current
})

function stateClass(index) {
	const state = stepState(index, currentIndex.value)
	const compact = props.size === "compact"
	if (state === "current") return "bg-surface-gray-7 text-ink-white font-semibold"
	// The thin bar has no labels, so done steps need a stronger fill to read as progress.
	if (state === "done") return compact ? "bg-surface-gray-4" : "bg-surface-gray-3 text-ink-gray-8"
	return compact ? "bg-surface-gray-2" : "bg-surface-gray-2 text-ink-gray-5"
}
</script>

<style scoped>
/* Same chevron geometry as .wp-steps on the event page. */
.stage-steps--full .stage-step {
	height: 34px;
	margin-right: -8px;
	padding-left: 10px;
	font-size: 13px;
	clip-path: polygon(0 0, calc(100% - 12px) 0, 100% 50%, calc(100% - 12px) 100%, 0 100%, 12px 50%);
}
.stage-steps--full .stage-step:first-child {
	padding-left: 0;
	border-radius: 8px 0 0 8px;
	clip-path: polygon(0 0, calc(100% - 12px) 0, 100% 50%, calc(100% - 12px) 100%, 0 100%);
}
.stage-steps--full .stage-step:last-child {
	margin-right: 0;
	border-radius: 0 8px 8px 0;
	clip-path: polygon(0 0, 100% 0, 100% 100%, 0 100%, 12px 50%);
}
.stage-steps--compact .stage-step {
	height: 6px;
	margin-right: -3px;
	clip-path: polygon(0 0, calc(100% - 4px) 0, 100% 50%, calc(100% - 4px) 100%, 0 100%, 4px 50%);
}
.stage-steps--compact .stage-step:first-child {
	border-radius: 3px 0 0 3px;
	clip-path: polygon(0 0, calc(100% - 4px) 0, 100% 50%, calc(100% - 4px) 100%, 0 100%);
}
.stage-steps--compact .stage-step:last-child {
	margin-right: 0;
	border-radius: 0 3px 3px 0;
	clip-path: polygon(0 0, 100% 0, 100% 100%, 0 100%, 4px 50%);
}
.stage-step-no {
	display: inline-grid;
	flex-shrink: 0;
	place-items: center;
	width: 18px;
	height: 18px;
	border-radius: 50%;
	background: rgb(0 0 0 / 8%);
	font-size: 11px;
	font-weight: 600;
}
[aria-current="step"] .stage-step-no {
	background: rgb(255 255 255 / 20%);
}
</style>
