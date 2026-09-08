<template>
	<!--
		Selection list for the cockpit master-detail split pane.
		Not frappe-ui ListView: that widget targets full doctype list pages,
		not a pane that also hosts Kanban/Calendar.
	-->
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
				<span v-if="!compact" class="text-xs font-semibold text-gray-500 dark:text-gray-400">
					{{ issue.name }}
				</span>
				<Badge :label="issue.status" :theme="statusTheme(issue.status)" size="sm" variant="subtle" />
				<Badge
					v-if="issue.priority && !compact"
					:label="issue.priority"
					:theme="priorityTheme(issue.priority)"
					size="sm"
					variant="subtle"
				/>
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
				<span v-if="creationValue(issue)">
					created on {{ formatDate(creationValue(issue)) }}
				</span>
				<span v-if="modifiedValue(issue)">
					last updated on {{ formatDate(modifiedValue(issue)) }}
				</span>
				<span title="Issue age">{{ ageLabel(issue) }}</span>
				<span v-if="issue.issue_type">{{ issue.issue_type }}</span>
				<span v-if="showCreator">created by {{ issue.owner_name || issue.owner }}</span>
				<span>{{ assigneeLabel(issue) }}</span>
			</div>
			<div
				v-else
				class="mt-0.5 flex flex-wrap gap-x-2 text-xs text-gray-500 dark:text-gray-400"
			>
				<span v-if="creationValue(issue)">
					created on {{ formatDate(creationValue(issue)) }}
				</span>
				<span v-if="modifiedValue(issue)">
					last updated on {{ formatDate(modifiedValue(issue)) }}
				</span>
				<span title="Issue age">{{ ageLabel(issue) }}</span>
			</div>
		</button>
	</div>
</template>

<script setup>
import { Badge } from "frappe-ui"
import { formatDate, formatIssueAge } from "@spa/utils/datetime"

defineProps({
	issues: { type: Array, default: () => [] },
	selectedName: { type: String, default: null },
	showCreator: { type: Boolean, default: false },
	compact: { type: Boolean, default: false },
})

const emit = defineEmits(["select"])

function creationValue(issue) {
	const raw = issue.creation || issue.opening_date || ""
	return raw ? String(raw).slice(0, 10) : ""
}

function modifiedValue(issue) {
	const raw = issue.modified || ""
	return raw ? String(raw).slice(0, 10) : ""
}

function ageLabel(issue) {
	const age = formatIssueAge(issue)
	if (!age || age === "—" || age === "Today") return age
	return `${age} old`
}

function statusTheme(status) {
	const map = {
		Open: "red",
		Replied: "blue",
		"On Hold": "orange",
		Resolved: "green",
		Closed: "gray",
	}
	return map[status] || "blue"
}

function priorityTheme(priority) {
	const p = (priority || "").toLowerCase()
	if (p === "high") return "red"
	if (p === "low") return "gray"
	return "orange"
}

function assigneeLabel(issue) {
	const names = issue.assignee_names || []
	if (!names.length) return "Unassigned"
	if (names.length === 1) return names[0]
	return `${names[0]} +${names.length - 1}`
}
</script>
