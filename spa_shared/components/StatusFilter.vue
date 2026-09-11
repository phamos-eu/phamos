<template>
	<div
		class="flex flex-nowrap items-center gap-2.5"
		role="group"
		aria-label="Filter by status"
	>
		<button
			v-for="status in statuses"
			:key="status"
			type="button"
			class="shrink-0 rounded-full"
			:class="
				isSelected(status)
					? 'origin-center scale-[1.2] z-[1]'
					: 'opacity-70 hover:opacity-100'
			"
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

const DEFAULT_THEMES = {
	Open: "red",
	Replied: "blue",
	"On Hold": "orange",
	Resolved: "green",
	Closed: "gray",
}

const DEFAULT_STRONG_CLASSES = {
	Open: "bg-red-600 text-white dark:bg-red-500",
	Replied: "bg-blue-600 text-white dark:bg-blue-500",
	"On Hold": "bg-amber-500 text-white dark:bg-amber-500",
	Resolved: "bg-green-600 text-white dark:bg-green-500",
	Closed: "bg-gray-700 text-white dark:bg-gray-500",
}

const props = defineProps({
	/** Currently selected status names (empty = all) */
	modelValue: { type: Array, default: () => [] },
	/** Available status names */
	statuses: {
		type: Array,
		default: () => ["Open", "Replied", "On Hold", "Resolved", "Closed"],
	},
	/** Optional frappe-ui Badge theme overrides keyed by status */
	themes: { type: Object, default: null },
	/** Optional selected-pill class overrides keyed by status */
	strongClasses: { type: Object, default: null },
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
	const map = props.themes || DEFAULT_THEMES
	return map[status] || "blue"
}

function statusStrongClass(status) {
	const map = props.strongClasses || DEFAULT_STRONG_CLASSES
	return map[status] || "bg-blue-600 text-white dark:bg-blue-500"
}
</script>
