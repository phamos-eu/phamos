<template>
	<div
		class="flex items-center"
		:class="wrap ? 'w-full flex-wrap justify-center gap-1' : 'flex-nowrap gap-2.5'"
		role="group"
		aria-label="Filter by status"
	>
		<button
			v-for="status in statuses"
			:key="status"
			type="button"
			class="shrink-0 rounded-full"
			:class="[
				isSelected(status) ? 'z-[1]' : 'opacity-70 hover:opacity-100',
				// Scaling the selected chip grows the row past its column and
				// overlaps its neighbours; where the chips wrap, the filled
				// style already says 'selected' on its own.
				isSelected(status) && !wrap ? 'origin-center scale-[1.2]' : '',
			]"
			:aria-pressed="isSelected(status)"
			@click="toggle(status)"
		>
			<!-- Wrapped chips are drawn here rather than by Badge, so they can be
			     compact enough for a long status set to settle on two rows. -->
			<span
				v-if="wrap"
				class="inline-flex h-[18px] items-center whitespace-nowrap rounded-full px-1.5 text-[11px] font-medium leading-none"
				:class="isSelected(status) ? statusStrongClass(status) : statusSubtleClass(status)"
			>
				{{ status }}
			</span>
			<span
				v-else-if="isSelected(status)"
				class="inline-flex h-5 items-center whitespace-nowrap rounded-full px-1.5 text-xs font-semibold"
				:class="statusStrongClass(status)"
			>
				{{ status }}
			</span>
			<Badge
				v-else
				class="whitespace-nowrap"
				:label="status"
				:theme="statusTheme(status)"
				size="sm"
				variant="subtle"
			/>
		</button>
	</div>
</template>

<script setup>
import { computed } from "vue"
import { Badge } from "frappe-ui"

const props = defineProps({
	/** Currently selected status names (empty = all) */
	modelValue: { type: Array, default: () => [] },
	/**
	 * Let the chips wrap onto several rows instead of one long line — for
	 * lists whose statuses are too many or too wordy to fit their column.
	 */
	wrap: { type: Boolean, default: false },
	/**
	 * Optional status → colour-theme map, so a list's filter chips match the
	 * badges in its own rows instead of falling back to this component's
	 * issue-oriented defaults.
	 */
	themes: { type: Object, default: null },
	/** Available status names */
	statuses: {
		type: Array,
		default: () => ["Open", "Replied", "On Hold", "Resolved", "Closed"],
	},
})

const emit = defineEmits(["update:modelValue"])

const selected = computed(() => new Set(props.modelValue || []))

function isSelected(status) {
	return selected.value.has(status)
}

function toggle(status) {
	const next = new Set(selected.value)
	if (next.has(status)) next.delete(status)
	else next.add(status)
	emit("update:modelValue", [...next])
}

function statusTheme(status) {
	if (props.themes?.[status]) return props.themes[status]
	const map = {
		Open: "red",
		Replied: "blue",
		"On Hold": "orange",
		Resolved: "green",
		Closed: "gray",
		"Not Started": "gray",
		"In Progress": "orange",
		Completed: "green",
	}
	return map[status] || "blue"
}

/** Unselected chips in wrap mode — Badge's own subtle look, at chip size. */
function statusSubtleClass(status) {
	const map = {
		red: "bg-red-50 text-red-700 dark:bg-red-900 dark:text-red-200",
		blue: "bg-blue-50 text-blue-700 dark:bg-blue-900 dark:text-blue-200",
		orange: "bg-amber-50 text-amber-700 dark:bg-amber-900 dark:text-amber-200",
		green: "bg-green-50 text-green-700 dark:bg-green-900 dark:text-green-200",
		gray: "bg-surface-gray-2 text-ink-gray-7",
	}
	return map[statusTheme(status)] || map.blue
}

const STRONG_BY_THEME = {
	red: "bg-red-600 text-white dark:bg-red-500",
	blue: "bg-blue-600 text-white dark:bg-blue-500",
	orange: "bg-amber-500 text-white dark:bg-amber-500",
	green: "bg-green-600 text-white dark:bg-green-500",
	gray: "bg-gray-700 text-white dark:bg-gray-500",
}

function statusStrongClass(status) {
	// A caller-supplied theme wins: without it this fell back to blue for every
	// status it didn't recognise by name, so a whole status set could light up
	// the same colour when selected.
	if (props.themes?.[status]) return STRONG_BY_THEME[props.themes[status]] || STRONG_BY_THEME.blue
	const map = {
		Open: "bg-red-600 text-white dark:bg-red-500",
		Replied: "bg-blue-600 text-white dark:bg-blue-500",
		"On Hold": "bg-amber-500 text-white dark:bg-amber-500",
		Resolved: "bg-green-600 text-white dark:bg-green-500",
		Closed: "bg-gray-700 text-white dark:bg-gray-500",
		"Not Started": "bg-gray-700 text-white dark:bg-gray-500",
		"In Progress": "bg-amber-500 text-white dark:bg-amber-500",
		Completed: "bg-green-600 text-white dark:bg-green-500",
	}
	return map[status] || STRONG_BY_THEME[statusTheme(status)] || STRONG_BY_THEME.blue
}
</script>
