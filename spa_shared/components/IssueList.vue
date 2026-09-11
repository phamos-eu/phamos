<template>
	<!--
		Selection list for the cockpit master-detail split pane.
		Not frappe-ui ListView: that widget targets full doctype list pages,
		not a pane that also hosts Kanban/Calendar.
		When alignWithFilters, root uses `contents` so rows join the parent subgrid.
	-->
	<div :class="alignWithFilters && !compact ? 'contents' : 'min-h-0 flex-1 overflow-y-auto'">
		<button
			v-for="issue in issues"
			:key="issue.name"
			type="button"
			class="border-b border-outline-gray-1 text-left hover:bg-surface-gray-2"
			:class="[
				alignWithFilters && !compact
					? [ISSUE_LIST_FILTER_SUBGRID, 'py-3']
					: compact
						? 'block w-full px-3 py-2.5'
						: 'block w-full px-5 py-3',
				{
					'bg-surface-gray-2 shadow-[inset_3px_0_0_0_var(--outline-gray-4)]':
						issue.name === selectedName,
				},
			]"
			@click="emit('select', issue.name)"
		>
			<template v-if="alignWithFilters && !compact">
				<div class="min-w-0">
					<div class="text-xs font-semibold text-ink-gray-6">
						{{ issue.name }}
					</div>
					<div
						class="truncate text-sm font-medium text-ink-gray-9"
						:title="issue.subject"
					>
						{{ issue.subject }}
					</div>
					<div
						v-if="metaParts(issue).length"
						class="mt-0.5 truncate text-xs text-ink-gray-6"
					>
						{{ metaParts(issue).join(" · ") }}
					</div>
				</div>
				<div class="flex min-w-0 justify-center">
					<Badge
						v-if="issue.priority"
						class="whitespace-nowrap"
						:label="issue.priority"
						:theme="priorityTheme(issue.priority)"
						size="sm"
						variant="subtle"
					/>
				</div>
				<div class="flex min-w-0 justify-center">
					<Badge
						class="whitespace-nowrap"
						:label="issue.status"
						:theme="statusTheme(issue.status)"
						size="sm"
						variant="subtle"
					/>
				</div>
				<div class="min-w-0 space-y-0.5 text-center text-xs text-ink-gray-6">
					<div v-if="creationValue(issue)">
						{{ formatDate(creationValue(issue)) }}
					</div>
					<div title="Issue age">{{ ageLabel(issue) }}</div>
				</div>
				<div class="min-w-0 text-center text-xs text-ink-gray-6">
					<div v-if="modifiedValue(issue)">
						{{ formatDate(modifiedValue(issue)) }}
					</div>
				</div>
				<!-- Desk list puts assignments on the right; align with New Issue column -->
				<div class="flex min-w-0 items-center justify-end pr-1">
					<AvatarGroup
						:users="assigneeUsersFromRow(issue)"
						:limit="3"
						align="right"
						:show-empty="false"
					/>
				</div>
			</template>
			<template v-else>
				<div class="mb-1 flex flex-wrap items-center gap-1.5">
					<span v-if="!compact" class="text-xs font-semibold text-ink-gray-6">
						{{ issue.name }}
					</span>
					<Badge
						class="whitespace-nowrap"
						:label="issue.status"
						:theme="statusTheme(issue.status)"
						size="sm"
						variant="subtle"
					/>
					<Badge
						v-if="issue.priority && !compact"
						class="whitespace-nowrap"
						:label="issue.priority"
						:theme="priorityTheme(issue.priority)"
						size="sm"
						variant="subtle"
					/>
				</div>
				<div
					class="font-medium text-ink-gray-9"
					:class="compact ? 'truncate text-sm' : 'mb-1 text-sm'"
					:title="issue.subject"
				>
					{{ issue.subject }}
				</div>
				<div
					v-if="!compact"
					class="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-gray-6"
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
					<AvatarGroup
						:users="assigneeUsersFromRow(issue)"
						:limit="3"
						align="right"
					/>
				</div>
				<div
					v-else
					class="mt-0.5 flex flex-wrap gap-x-2 text-xs text-ink-gray-6"
				>
					<span v-if="creationValue(issue)">
						created on {{ formatDate(creationValue(issue)) }}
					</span>
					<span v-if="modifiedValue(issue)">
						last updated on {{ formatDate(modifiedValue(issue)) }}
					</span>
					<span title="Issue age">{{ ageLabel(issue) }}</span>
				</div>
			</template>
		</button>
	</div>
</template>

<script setup>
import { Badge } from "frappe-ui"
import AvatarGroup from "@spa/components/AvatarGroup.vue"
import { ISSUE_LIST_FILTER_SUBGRID } from "@spa/issueListColumns.js"
import { assigneeUsersFromRow } from "@spa/utils/avatar.js"
import { formatDate, formatIssueAge } from "@spa/utils/datetime"

const props = defineProps({
	issues: { type: Array, default: () => [] },
	selectedName: { type: String, default: null },
	showCreator: { type: Boolean, default: false },
	compact: { type: Boolean, default: false },
	/** Align columns with IssuesInbox Priority / Status / date sort filters */
	alignWithFilters: { type: Boolean, default: false },
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

function metaParts(issue) {
	const parts = []
	if (issue.issue_type) parts.push(issue.issue_type)
	if (props.showCreator) parts.push(`created by ${issue.owner_name || issue.owner}`)
	return parts
}
</script>
