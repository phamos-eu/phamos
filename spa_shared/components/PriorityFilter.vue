<template>
	<div
		v-if="priorities.length"
		class="flex flex-wrap items-center gap-2.5"
		role="group"
		aria-label="Filter by priority"
	>
		<button
			v-for="priority in priorities"
			:key="priority"
			type="button"
			class="rounded-full"
			:class="
				isSelected(priority)
					? 'origin-center scale-[1.2] z-[1]'
					: 'opacity-70 hover:opacity-100'
			"
			:aria-pressed="isSelected(priority)"
			@click="toggle(priority)"
		>
			<span
				v-if="isSelected(priority)"
				class="inline-flex h-5 items-center rounded-full px-1.5 text-xs font-semibold"
				:class="priorityStrongClass(priority)"
			>
				{{ priority }}
			</span>
			<Badge
				v-else
				:label="priority"
				:theme="priorityTheme(priority)"
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
	/** Currently selected priority names (empty = all) */
	modelValue: { type: Array, default: () => [] },
	/** Available priority names from Issue Priority */
	priorities: { type: Array, default: () => [] },
})

const emit = defineEmits(["update:modelValue"])

const selected = computed(() => new Set(props.modelValue || []))

function isSelected(priority) {
	return selected.value.has(priority)
}

function toggle(priority) {
	const next = new Set(selected.value)
	if (next.has(priority)) next.delete(priority)
	else next.add(priority)
	emit("update:modelValue", [...next])
}

function priorityTheme(priority) {
	const p = (priority || "").toLowerCase()
	if (p === "high") return "red"
	if (p === "low") return "gray"
	return "orange"
}

function priorityStrongClass(priority) {
	const p = (priority || "").toLowerCase()
	if (p === "high" || p === "urgent") {
		return "bg-red-600 text-white dark:bg-red-500"
	}
	if (p === "low") {
		return "bg-gray-700 text-white dark:bg-gray-500"
	}
	return "bg-amber-500 text-white dark:bg-amber-500"
}
</script>
