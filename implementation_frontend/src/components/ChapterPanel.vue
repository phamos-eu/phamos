<template>
	<!-- One chapter of the Roadmap beside the timeline (#2035): its plan, slack and baseline
	     shift, the chapters it waits for and those waiting for it, and its features. A module
	     row without a chapter shows the module's own plan and how to make it plannable. -->
	<aside class="flex min-h-0 flex-col rounded-lg border border-outline-gray-2 bg-surface-white" :aria-label="__('Chapter')">
		<div class="flex items-start gap-2 border-b border-outline-gray-1 px-4 py-2.5">
			<div class="min-w-0 flex-1">
				<div class="text-xs text-ink-gray-5">
					{{ bar.module || __("No module") }}<template v-if="bar.status"> · <StatusBadge :status="bar.status" /></template>
				</div>
				<h2 class="mt-0.5 text-base font-semibold leading-snug text-ink-gray-9">{{ bar.title || bar.name }}</h2>
			</div>
			<button type="button" class="rounded p-1 text-ink-gray-5 hover:bg-surface-gray-2 hover:text-ink-gray-9" :aria-label="__('Close')" :title="__('Close (Esc)')" @click="$emit('close')">
				<FeatherIcon name="x" class="h-4 w-4" />
			</button>
		</div>

		<div class="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-4 py-3 text-sm">
			<dl class="grid grid-cols-2 gap-x-4 gap-y-1.5">
				<div v-for="fact in facts" :key="fact.label" class="min-w-0">
					<dt class="text-xs text-ink-gray-5">{{ fact.label }}</dt>
					<dd class="break-words" :class="fact.tone || 'text-ink-gray-8'">{{ fact.value }}</dd>
				</div>
			</dl>

			<p v-if="!bar.chapter" class="rounded-lg bg-surface-gray-2 px-3 py-2 text-xs text-ink-gray-7">
				{{ __("This module is planned without a chapter. A chapter makes it plannable with dependencies and the critical path.") }}
			</p>

			<a
				v-if="bar.chapter && canPropose"
				:href="proposeUrl"
				target="_blank"
				rel="noopener noreferrer"
				class="inline-flex w-fit items-center gap-1.5 rounded border border-outline-gray-2 px-2 py-1 text-sm text-ink-gray-8 hover:bg-surface-gray-2"
			>
				<FeatherIcon name="edit-3" class="h-3.5 w-3.5" />
				{{ __("Propose a date change") }}
				<FeatherIcon name="external-link" class="h-3 w-3 text-ink-gray-5" />
			</a>

			<section v-for="group in linkGroups" :key="group.label">
				<h3 class="text-xs font-medium uppercase tracking-wide text-ink-gray-5">{{ group.label }}</h3>
				<button
					v-for="linked in group.bars"
					:key="linked.name"
					type="button"
					class="flex w-full items-center gap-2 py-0.5 text-left text-ink-gray-8 hover:text-ink-gray-9 hover:underline"
					@click="$emit('select-chapter', linked.name)"
				>
					<FeatherIcon name="git-commit" class="h-3.5 w-3.5 shrink-0 text-ink-gray-5" />
					<span class="min-w-0 flex-1 truncate">{{ linked.title || linked.name }}</span>
					<span class="shrink-0 text-xs text-ink-gray-5">{{ date(linked.target_date) }}</span>
				</button>
			</section>

			<section v-if="bar.chapter">
				<h3 class="text-xs font-medium uppercase tracking-wide text-ink-gray-5">{{ __("Features") }}</h3>
				<p v-if="featuresError" class="mt-1 text-ink-red-4">{{ featuresError }}</p>
				<p v-else-if="features === null" class="mt-1 text-ink-gray-5">{{ __("Loading…") }}</p>
				<p v-else-if="!features.length" class="mt-1 text-ink-gray-5">{{ __("No features here yet.") }}</p>
				<button
					v-for="f in features || []"
					:key="f.name"
					type="button"
					class="flex w-full items-center gap-2 py-0.5 text-left text-ink-gray-8 hover:text-ink-gray-9"
					@click="$emit('open-feature', f.name)"
				>
					<span class="min-w-0 flex-1 truncate hover:underline">{{ f.title }}</span>
					<StatusBadge :status="f.status" />
				</button>
			</section>
		</div>
	</aside>
</template>

<script setup>
import { computed } from "vue"
import dayjs from "dayjs"
import { FeatherIcon } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"
import StatusBadge from "./StatusBadge.vue"
import { levelStep, proposeDateChangeUrl } from "../utils/roadmapView.js"

const props = defineProps({
	implementation: { type: String, required: true },
	/** a bar of get_roadmap with its `module` (barsByName) */
	bar: { type: Object, required: true },
	/** { dependsOn, neededBy }: bars (chapterLinks) */
	links: { type: Object, default: () => ({ dependsOn: [], neededBy: [] }) },
	/** the chapter's features from get_features; null while loading */
	features: { type: Array, default: null },
	/** shown instead of the list when get_features failed */
	featuresError: { type: String, default: "" },
	canPropose: { type: Boolean, default: false },
})
defineEmits(["close", "select-chapter", "open-feature"])

const proposeUrl = computed(() => proposeDateChangeUrl(props.implementation, props.bar.chapter))

const facts = computed(() => {
	const b = props.bar
	const out = [
		{ label: __("Planned start"), value: date(b.planned_start) },
		{ label: __("Target date"), value: date(b.target_date) },
		{ label: __("Levels"), value: levels(b) },
	]
	// with a baseline the step starts at the agreed level, so the current one needs its own line
	if (b.start_level) out.push({ label: __("Current Level"), value: b.current_level ? `L${b.current_level}` : "—" })
	if (b.chapter) out.push(slack(b))
	if (b.baseline) {
		const shift = b.baseline.shift_days
		out.push({
			label: __("Against the baseline"),
			value: shift === null || shift === undefined ? "—" : shift ? (shift > 0 ? __("+{0} d", [shift]) : __("{0} d", [shift])) : __("On plan"),
			tone: shift > 0 ? "text-ink-amber-3" : null,
		})
	} else if (b.is_new) {
		out.push({ label: __("Against the baseline"), value: __("Added after the baseline") })
	}
	return out
})

const linkGroups = computed(() =>
	[
		{ label: __("Depends on"), bars: props.links.dependsOn },
		{ label: __("Needed by"), bars: props.links.neededBy },
	].filter((g) => g.bars.length)
)

function levels(b) {
	// the same step as on the bar (levelStep)
	const step = levelStep(b)
	if (!step.to) return step.current ? `L${step.current}` : "—"
	// no level to start from: only the target, as the bar draws no step either
	if (!step.from) return `→ L${step.to}`
	return __("L{0} → L{1}", [step.from, step.to])
}

function slack(b) {
	const label = __("Slack to the end date")
	if (b.done) return { label, value: __("Target level reached"), tone: "text-ink-green-3" }
	if (b.cycle) return { label, value: __("In a dependency loop"), tone: "text-ink-red-4" }
	if (b.slack_days === null || b.slack_days === undefined) return { label, value: "—" }
	if (b.slack_days < 0) return { label, value: __("{0} d late", [-b.slack_days]), tone: "text-ink-red-4" }
	if (b.slack_days === 0) return { label, value: __("On the critical path"), tone: "font-medium text-ink-gray-9" }
	return { label, value: __("{0} d slack", [b.slack_days]) }
}

function date(value) {
	return value ? dayjs(value).format("D MMM YYYY") : "—"
}
</script>
