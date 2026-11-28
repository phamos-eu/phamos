<template>
	<section class="rounded-lg border border-outline-gray-2 bg-surface-white p-5" :aria-label="challenge.title">
		<div class="flex items-start gap-4">
			<svg class="h-16 w-16 flex-none -rotate-90" viewBox="0 0 64 64" aria-hidden="true">
				<circle cx="32" cy="32" r="27" fill="none" stroke-width="6" style="stroke: var(--surface-gray-3)" />
				<circle
					cx="32"
					cy="32"
					r="27"
					fill="none"
					stroke-width="6"
					stroke-linecap="round"
					:stroke-dasharray="`${dash} ${CIRCUMFERENCE}`"
					style="stroke: var(--ink-green-3)"
				/>
			</svg>
			<div class="min-w-0 flex-1">
				<div class="flex items-start justify-between gap-2">
					<h2 class="text-base font-semibold text-ink-gray-9">{{ challenge.title }}</h2>
					<Dropdown v-if="challenge.status === 'Active'" :options="menu" placement="right">
						<Button variant="ghost" size="sm" :aria-label="__('Challenge options')">
							<FeatherIcon name="more-horizontal" class="h-4 w-4" />
						</Button>
					</Dropdown>
				</div>
				<p class="text-sm font-medium text-ink-gray-8">
					{{ challenge.status === "Active" ? progressText(challenge) : finishedText(challenge) }}
					<span v-if="streak" class="ml-2 text-xs font-normal text-ink-gray-5">{{ streak }}</span>
				</p>
				<template v-if="challenge.status === 'Active'">
					<p v-if="welcome" class="mt-1 text-sm text-ink-gray-7">{{ welcome }}</p>
					<p class="mt-1 text-sm text-ink-gray-7">{{ todayText(challenge, formatDate) }}</p>
					<p v-if="repair" class="mt-1 text-sm text-ink-gray-7">{{ repair }}</p>
					<p class="mt-1 text-xs text-ink-gray-5">{{ jokerText(challenge) }}</p>
				</template>
			</div>
		</div>

		<ol class="mt-4 flex flex-wrap gap-1" :aria-label="__('Days of the challenge')">
			<li
				v-for="day in challenge.days"
				:key="day.date"
				class="h-3.5 w-3.5 rounded-sm"
				:style="dayStyle(day)"
				:title="dayTitle(day)"
			/>
		</ol>
	</section>
</template>

<script setup>
import { computed } from "vue"
import { Dropdown } from "frappe-ui"
import { formatDate } from "@spa/utils/datetime.js"
import { __ } from "@spa/utils/i18n.js"
import {
	dayState,
	finishedText,
	jokerText,
	progressText,
	repairText,
	ringFraction,
	streakText,
	todayText,
	welcomeText,
} from "@spa/utils/challengeProgress.js"

const props = defineProps({
	challenge: { type: Object, required: true },
})
const emit = defineEmits(["end"])

const CIRCUMFERENCE = 2 * Math.PI * 27
const dash = computed(() => ringFraction(props.challenge) * CIRCUMFERENCE)
const streak = computed(() => streakText(props.challenge))
const welcome = computed(() => welcomeText(props.challenge))
const repair = computed(() => repairText(props.challenge))
const menu = computed(() => [{ label: __("End this challenge"), icon: "flag", onClick: () => emit("end", props.challenge) }])

const TONES = {
	met: "background: var(--ink-green-3)",
	joker: "background: var(--ink-amber-3)",
	open: "background: transparent; box-shadow: inset 0 0 0 1px var(--outline-gray-4)",
	today: "background: var(--surface-gray-3); box-shadow: inset 0 0 0 2px var(--ink-gray-7)",
	upcoming: "background: var(--surface-gray-3)",
}

function dayTitle(day) {
	const date = formatDate(day.date)
	const state = dayState(day.result).label
	if (day.closes == null) return `${date}: ${state}`
	return props.challenge.split
		? __("{0}: {1} ({2} planned, {3} spontaneous)", [date, state, day.planned, day.spontaneous])
		: __("{0}: {1} ({2} closed)", [date, state, day.closes])
}

function dayStyle(day) {
	if (day.result === "Today" && (day.met ?? day.closes >= day.target)) return `${TONES.met}; box-shadow: inset 0 0 0 2px var(--ink-gray-7)`
	return TONES[dayState(day.result).tone]
}
</script>
