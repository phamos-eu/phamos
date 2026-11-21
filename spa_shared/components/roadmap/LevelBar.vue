<template>
	<!-- One chapter as a level-step bar (#2034): "L2 → L4" with the current level as fill.
	     Positioned by the parent through `rect`; a focusable button for the keyboard path. -->
	<div
		role="button"
		tabindex="0"
		class="roadmap-level-bar"
		:class="{
			'roadmap-level-bar--critical': bar.critical,
			'roadmap-level-bar--faded': bar.faded,
			'roadmap-level-bar--selected': selected,
			'roadmap-level-bar--clipped-start': rect.clippedStart,
			'roadmap-level-bar--clipped-end': rect.clippedEnd,
		}"
		:style="{ left: `${rect.left}px`, top: `${rect.top}px`, width: `${rect.width}px`, height: `${rect.height}px` }"
		:aria-pressed="selected ? 'true' : 'false'"
		:aria-label="ariaLabel"
		:title="title"
	>
		<div v-if="fill !== null" class="roadmap-level-bar__fill" :style="{ width: `${fill * 100}%` }" />
		<span class="roadmap-level-bar__text">
			<span v-if="levelStep" class="roadmap-level-bar__step">{{ levelStep }}</span>
			<span class="truncate">{{ bar.label || bar.name }}</span>
		</span>
	</div>
</template>

<script setup>
import { computed } from "vue"
import { __ } from "@spa/utils/i18n.js"
import { formatDate } from "@spa/utils/datetime.js"
import { isoDay, levelFill } from "@spa/utils/roadmapLayout.js"

const props = defineProps({
	/** { name, label, start, end, fromLevel, toLevel, currentLevel, critical, faded } */
	bar: { type: Object, required: true },
	/** { left, top, width, height, clippedStart, clippedEnd } in px */
	rect: { type: Object, required: true },
	selected: { type: Boolean, default: false },
})

const fill = computed(() => levelFill(props.bar.currentLevel, props.bar.toLevel, props.bar.fromLevel))

const levelStep = computed(() => {
	const { fromLevel, toLevel } = props.bar
	if (fill.value === null) return ""
	return __("L{0} → L{1}", [fromLevel, toLevel])
})

const ariaLabel = computed(() => [props.bar.label || props.bar.name, levelStep.value].filter(Boolean).join(", "))

const title = computed(() => {
	const lines = [props.bar.label || props.bar.name]
	if (levelStep.value) {
		lines.push(`${levelStep.value} · ${__("Current Level")}: ${props.bar.currentLevel ?? props.bar.fromLevel}`)
	}
	lines.push(`${formatDate(isoDay(props.bar.start))} – ${formatDate(isoDay(props.bar.end))}`)
	if (props.bar.critical) lines.push(__("On the critical path"))
	return lines.join("\n")
})
</script>

<style scoped>
.roadmap-level-bar {
	position: absolute;
	overflow: hidden;
	border: 1px solid var(--outline-gray-3);
	border-radius: 4px;
	background: var(--surface-gray-2);
	color: var(--ink-gray-8);
	cursor: pointer;
}

.roadmap-level-bar--clipped-start {
	border-left-style: dashed;
	border-top-left-radius: 0;
	border-bottom-left-radius: 0;
}

.roadmap-level-bar--clipped-end {
	border-right-style: dashed;
	border-top-right-radius: 0;
	border-bottom-right-radius: 0;
}

.roadmap-level-bar__fill {
	position: absolute;
	inset: 0 auto 0 0;
	background: var(--ink-blue-2);
	opacity: 0.35;
}

.roadmap-level-bar__text {
	position: relative;
	display: flex;
	height: 100%;
	align-items: center;
	gap: 4px;
	padding: 0 4px;
	font-size: 10px;
	line-height: 1;
	white-space: nowrap;
}

.roadmap-level-bar__step {
	flex-shrink: 0;
	font-weight: 600;
}

.roadmap-level-bar--critical {
	border: 2px solid var(--ink-red-3);
}

.roadmap-level-bar--faded {
	opacity: 0.45;
	border-style: dashed;
}

.roadmap-level-bar:hover {
	border-color: var(--ink-gray-5);
}

.roadmap-level-bar--critical:hover {
	border-color: var(--ink-red-4);
}

.roadmap-level-bar--selected,
.roadmap-level-bar:focus-visible {
	outline: 2px solid var(--ink-blue-3);
	outline-offset: 1px;
}
</style>
