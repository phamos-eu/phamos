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
				:class="MIS_STATUS_STRONG_CLASSES[status] || 'bg-blue-600 text-white'"
			>
				{{ status }}
			</span>
			<Badge
				v-else
				class="whitespace-nowrap"
				:label="status"
				:theme="misStatusTheme(status)"
				size="sm"
				variant="subtle"
			/>
		</button>
	</div>
</template>

<script setup>
import { computed } from "vue"
import { Badge } from "frappe-ui"
import {
	MIS_STATUSES,
	MIS_STATUS_STRONG_CLASSES,
	misStatusTheme,
} from "../misListColumns.js"

const props = defineProps({
	modelValue: { type: Array, default: () => [] },
	statuses: { type: Array, default: () => MIS_STATUSES },
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
</script>
