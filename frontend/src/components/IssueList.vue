<template>
	<div class="min-h-0 flex-1 overflow-y-auto">
		<button
			v-for="issue in issues"
			:key="issue.name"
			type="button"
			class="block w-full border-b border-gray-100 px-5 py-3 text-left hover:bg-gray-50"
			:class="{ 'bg-gray-50 shadow-[inset_3px_0_0_0_#111827]': issue.name === selectedName }"
			@click="emit('select', issue.name)"
		>
			<div class="mb-1 flex flex-wrap items-center gap-2">
				<span class="text-xs font-semibold text-gray-500">{{ issue.name }}</span>
				<span
					class="rounded-full px-2 py-0.5 text-[11px] font-semibold"
					:class="statusClass(issue.status)"
				>
					{{ issue.status }}
				</span>
				<span
					v-if="issue.priority"
					class="rounded-full px-2 py-0.5 text-[11px] font-semibold"
					:class="priorityClass(issue.priority)"
				>
					{{ issue.priority }}
				</span>
			</div>
			<div class="mb-1 text-sm font-medium text-gray-900">{{ issue.subject }}</div>
			<div class="flex flex-wrap gap-x-3 gap-y-1 text-xs text-gray-500">
				<span v-if="issue.issue_type">{{ issue.issue_type }}</span>
				<span v-if="showCreator">by {{ issue.owner_name || issue.owner }}</span>
				<span>{{ assigneeLabel(issue) }}</span>
				<span>{{ prettyDate(issue.modified) }}</span>
			</div>
		</button>
	</div>
</template>

<script setup>
defineProps({
	issues: { type: Array, default: () => [] },
	selectedName: { type: String, default: null },
	showCreator: { type: Boolean, default: false },
})

const emit = defineEmits(["select"])

function statusClass(status) {
	const map = {
		Open: "bg-blue-50 text-blue-700",
		Replied: "bg-violet-50 text-violet-700",
		"On Hold": "bg-amber-50 text-amber-700",
		Resolved: "bg-emerald-50 text-emerald-700",
		Closed: "bg-gray-100 text-gray-600",
	}
	return map[status] || map.Open
}

function priorityClass(priority) {
	const p = (priority || "").toLowerCase()
	if (p === "high") return "bg-red-50 text-red-700"
	if (p === "low") return "bg-yellow-50 text-yellow-700"
	return "bg-orange-50 text-orange-700"
}

function assigneeLabel(issue) {
	const names = issue.assignee_names || []
	if (!names.length) return "Unassigned"
	if (names.length === 1) return names[0]
	return `${names[0]} +${names.length - 1}`
}

function prettyDate(value) {
	if (!value) return ""
	try {
		return new Date(value).toLocaleString()
	} catch (e) {
		return value
	}
}
</script>
