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
						v-for="task in byStatus[col] || []"
						:key="task.name"
						draggable="true"
						class="cursor-pointer rounded-md border border-gray-200 bg-white px-2.5 py-2 shadow-sm hover:border-gray-300 dark:border-gray-700 dark:bg-gray-900 dark:hover:border-gray-600"
						:class="{
							'ring-2 ring-gray-900 ring-offset-1 dark:ring-gray-100 dark:ring-offset-gray-900': task.name === selectedName,
						}"
						@dragstart="onDragStart(task, $event)"
						@click="emit('select', task.name)"
					>
						<div class="mb-1 text-[11px] font-semibold text-gray-500 dark:text-gray-400">{{ task.name }}</div>
						<div class="mb-1 text-sm font-medium leading-snug text-gray-900 dark:text-gray-100">
							{{ task.subject }}
						</div>
						<div v-if="task.exp_start_date" class="text-[11px] text-gray-500 dark:text-gray-400">
							{{ formatDate(task.exp_start_date) }}
							<span v-if="task.exp_end_date"> → {{ formatDate(task.exp_end_date) }}</span>
						</div>
					</div>
				</div>
			</div>
		</div>
	</div>
</template>

<script setup>
import { computed } from "vue"
import { formatDate } from "@spa/utils/datetime"

const COLUMNS = ["Open", "Working", "Pending Review", "Overdue", "Completed"]

const props = defineProps({
	tasks: { type: Array, default: () => [] },
	selectedName: { type: String, default: null },
})

const emit = defineEmits(["select", "status-change"])

const columns = COLUMNS

const byStatus = computed(() => {
	const map = Object.fromEntries(COLUMNS.map((c) => [c, []]))
	for (const task of props.tasks) {
		const status = COLUMNS.includes(task.status) ? task.status : "Open"
		map[status].push(task)
	}
	return map
})

function onDragStart(task, event) {
	event.dataTransfer.setData("text/plain", task.name)
	event.dataTransfer.effectAllowed = "move"
}

function onDrop(col, event) {
	const name = event.dataTransfer.getData("text/plain")
	if (!name) return
	const task = props.tasks.find((t) => t.name === name)
	if (!task || task.status === col) return
	emit("status-change", { name, status: col })
}
</script>
