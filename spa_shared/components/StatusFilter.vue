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
			<span
				v-if="isSelected(status)"
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

function statusStrongClass(status) {
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
	return map[status] || "bg-blue-600 text-white dark:bg-blue-500"
}
</script>
