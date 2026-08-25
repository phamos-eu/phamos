<template>
	<div class="min-h-0 flex-1 overflow-x-auto overflow-y-hidden">
		<div class="flex h-full min-h-[280px] gap-3 p-3">
			<div
				v-for="col in columns"
				:key="col"
				class="flex w-56 flex-none flex-col rounded-lg bg-gray-50 dark:bg-gray-800/60"
				@dragover.prevent
				@drop="onDrop(col, $event)"
			>
				<div
					class="flex flex-shrink-0 items-center justify-between border-b border-gray-200 px-3 py-2 dark:border-gray-700"
				>
					<span class="text-xs font-semibold uppercase tracking-wide text-gray-600 dark:text-gray-400">
						{{ col }}
					</span>
					<span class="rounded-full bg-white px-1.5 py-0.5 text-[11px] text-gray-500 dark:bg-gray-900 dark:text-gray-400">
						{{ byStatus[col]?.length || 0 }}
					</span>
				</div>
				<div class="min-h-0 flex-1 space-y-2 overflow-y-auto p-2">
					<div
						v-for="issue in byStatus[col] || []"
						:key="issue.name"
						draggable="true"
						class="cursor-pointer rounded-md border border-gray-200 bg-white px-2.5 py-2 shadow-sm hover:border-gray-300 dark:border-gray-700 dark:bg-gray-900 dark:hover:border-gray-600"
						:class="{
							'ring-2 ring-gray-900 ring-offset-1 dark:ring-gray-100 dark:ring-offset-gray-900':
								issue.name === selectedName,
						}"
						@dragstart="onDragStart(issue, $event)"
						@click="emit('select', issue.name)"
					>
						<div class="mb-1 text-[11px] font-semibold text-gray-500 dark:text-gray-400">{{ issue.name }}</div>
						<div class="mb-1 text-sm font-medium leading-snug text-gray-900 dark:text-gray-100">
							{{ issue.subject }}
						</div>
						<span
							v-if="issue.priority"
							class="rounded-full px-2 py-0.5 text-[11px] font-semibold"
							:class="priorityClass(issue.priority)"
						>
							{{ issue.priority }}
						</span>
					</div>
				</div>
			</div>
		</div>
	</div>
</template>

<script setup>
import { computed } from "vue"

const COLUMNS = ["Open", "Replied", "On Hold", "Resolved", "Closed"]

const props = defineProps({
	issues: { type: Array, default: () => [] },
	selectedName: { type: String, default: null },
})

const emit = defineEmits(["select", "status-change"])

const columns = COLUMNS

const byStatus = computed(() => {
	const map = Object.fromEntries(COLUMNS.map((c) => [c, []]))
	for (const issue of props.issues) {
		const status = COLUMNS.includes(issue.status) ? issue.status : "Open"
		map[status].push(issue)
	}
	return map
})

function priorityClass(priority) {
	const p = (priority || "").toLowerCase()
	if (p === "high") return "bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300"
	if (p === "low") return "bg-yellow-50 text-yellow-700 dark:bg-yellow-950 dark:text-yellow-300"
	return "bg-orange-50 text-orange-700 dark:bg-orange-950 dark:text-orange-300"
}

function onDragStart(issue, event) {
	event.dataTransfer.setData("text/plain", issue.name)
	event.dataTransfer.effectAllowed = "move"
}

function onDrop(status, event) {
	const name = event.dataTransfer.getData("text/plain")
	if (!name) return
	const issue = props.issues.find((i) => i.name === name)
	if (!issue || issue.status === status) return
	emit("status-change", { name, status })
}
</script>
