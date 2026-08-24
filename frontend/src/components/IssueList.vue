<template>
	<div class="min-h-0 flex-1 overflow-y-auto">
		<button
			v-for="issue in issues"
			:key="issue.name"
			type="button"
			class="block w-full border-b border-gray-100 text-left hover:bg-gray-50 dark:border-gray-800 dark:hover:bg-gray-800/60"
			:class="[
				compact ? 'px-3 py-2.5' : 'px-5 py-3',
				{
					'bg-gray-50 shadow-[inset_3px_0_0_0_#111827] dark:bg-gray-800 dark:shadow-[inset_3px_0_0_0_#f3f4f6]':
						issue.name === selectedName,
				},
			]"
			@click="emit('select', issue.name)"
		>
			<div class="mb-1 flex flex-wrap items-center gap-1.5">
				<span
					v-if="!compact"
					class="text-xs font-semibold text-gray-500 dark:text-gray-400"
				>
					{{ issue.name }}
				</span>
				<span
					class="rounded-full px-1.5 py-0.5 text-[10px] font-semibold"
					:class="statusClass(issue.status)"
				>
					{{ issue.status }}
				</span>
				<span
					v-if="issue.priority && !compact"
					class="rounded-full px-2 py-0.5 text-[11px] font-semibold"
					:class="priorityClass(issue.priority)"
				>
					{{ issue.priority }}
				</span>
			</div>
			<div
				class="font-medium text-gray-900 dark:text-gray-100"
				:class="compact ? 'truncate text-sm' : 'mb-1 text-sm'"
				:title="issue.subject"
			>
				{{ issue.subject }}
			</div>
			<div
				v-if="!compact"
				class="flex flex-wrap gap-x-3 gap-y-1 text-xs text-gray-500 dark:text-gray-400"
			>
				<span v-if="issue.issue_type">{{ issue.issue_type }}</span>
				<span v-if="showCreator">by {{ issue.owner_name || issue.owner }}</span>
				<span>{{ assigneeLabel(issue) }}</span>
				<span>{{ formatDatetime(issue.modified) }}</span>
			</div>
		</button>
	</div>
</template>

<script setup>
import { formatDatetime } from "../utils/datetime"

defineProps({
	issues: { type: Array, default: () => [] },
	selectedName: { type: String, default: null },
	showCreator: { type: Boolean, default: false },
	compact: { type: Boolean, default: false },
})

const emit = defineEmits(["select"])

function statusClass(status) {
	const map = {
		Open: "bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-300",
		Replied: "bg-violet-50 text-violet-700 dark:bg-violet-950 dark:text-violet-300",
		"On Hold": "bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
		Resolved: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300",
		Closed: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
	}
	return map[status] || map.Open
}

function priorityClass(priority) {
	const p = (priority || "").toLowerCase()
	if (p === "high") return "bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300"
	if (p === "low") return "bg-yellow-50 text-yellow-700 dark:bg-yellow-950 dark:text-yellow-300"
	return "bg-orange-50 text-orange-700 dark:bg-orange-950 dark:text-orange-300"
}

function assigneeLabel(issue) {
	const names = issue.assignee_names || []
	if (!names.length) return "Unassigned"
	if (names.length === 1) return names[0]
	return `${names[0]} +${names.length - 1}`
}
</script>
