<template>
	<!--
		Selection list for the cockpit master-detail split pane.
		Not frappe-ui ListView: that widget targets full doctype list pages,
		not a pane that also hosts Kanban/Gantt/Calendar.
	-->
	<div class="min-h-0 flex-1 overflow-y-auto">
		<button
			v-for="task in tasks"
			:key="task.name"
			type="button"
			class="block w-full border-b border-gray-100 px-5 py-3 text-left hover:bg-gray-50 dark:border-gray-800 dark:hover:bg-gray-800/60"
			:class="{
				'bg-gray-50 shadow-[inset_3px_0_0_0_#111827] dark:bg-gray-800 dark:shadow-[inset_3px_0_0_0_#f3f4f6]':
					task.name === selectedName,
			}"
			@click="emit('select', task.name)"
		>
			<div class="mb-1 flex flex-wrap items-center gap-1.5">
				<span class="text-xs font-semibold text-gray-500 dark:text-gray-400">{{ task.name }}</span>
				<Badge :label="task.status" :theme="statusTheme(task.status)" size="sm" variant="subtle" />
				<Badge
					v-if="task.priority"
					:label="task.priority"
					:theme="priorityTheme(task.priority)"
					size="sm"
					variant="subtle"
				/>
			</div>
			<div class="mb-1 text-sm font-medium text-gray-900 dark:text-gray-100" :title="task.subject">
				{{ task.subject }}
			</div>
			<div class="flex flex-wrap gap-x-3 gap-y-1 text-xs text-gray-500 dark:text-gray-400">
				<span v-if="task.project">{{ task.project }}</span>
				<span>{{ assigneeLabel(task) }}</span>
				<span v-if="task.exp_start_date || task.exp_end_date">
					{{ formatDate(task.exp_start_date) }}
					<span v-if="task.exp_end_date"> → {{ formatDate(task.exp_end_date) }}</span>
				</span>
			</div>
		</button>
	</div>
</template>

<script setup>
import { Badge } from "frappe-ui"
import { formatDate } from "@spa/utils/datetime"

defineProps({
	tasks: { type: Array, default: () => [] },
	selectedName: { type: String, default: null },
})

const emit = defineEmits(["select"])

function statusTheme(status) {
	const map = {
		Open: "blue",
		Working: "orange",
		"Pending Review": "orange",
		Overdue: "red",
		Completed: "green",
	}
	return map[status] || "gray"
}

function priorityTheme(priority) {
	const p = (priority || "").toLowerCase()
	if (p === "high") return "red"
	if (p === "low") return "gray"
	return "orange"
}

function assigneeLabel(task) {
	const names = task.assignee_names || []
	if (!names.length) return "Unassigned"
	if (names.length === 1) return names[0]
	return `${names[0]} +${names.length - 1}`
}
</script>
