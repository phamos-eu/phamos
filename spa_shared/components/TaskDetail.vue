<template>
	<div class="flex h-full flex-col">
		<header class="flex flex-shrink-0 items-start justify-between gap-4 border-b border-gray-200 px-5 py-4 dark:border-gray-800">
			<div class="min-w-0 flex-1">
				<div class="mb-1 text-xs font-semibold text-gray-500 dark:text-gray-400">{{ task.name }}</div>
				<h2 class="text-lg font-semibold text-gray-900 dark:text-gray-100">{{ task.subject }}</h2>
			</div>
			<div class="flex items-center gap-2">
				<a
					:href="task.desk_url"
					target="_blank"
					rel="noopener"
					class="rounded-md border border-gray-200 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800"
				>
					Open in Desk
				</a>
				<button
					class="rounded-md px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800"
					@click="emit('close')"
				>
					Close
				</button>
			</div>
		</header>

		<div class="flex-1 space-y-5 overflow-y-auto px-5 py-4 text-gray-900 dark:text-gray-100">
			<div class="grid grid-cols-2 gap-4 text-sm">
				<div>
					<div class="text-xs font-medium text-gray-500 dark:text-gray-400">Status</div>
					<div>{{ task.status || "—" }}</div>
				</div>
				<div>
					<div class="text-xs font-medium text-gray-500 dark:text-gray-400">Priority</div>
					<div>{{ task.priority || "—" }}</div>
				</div>
				<div>
					<div class="text-xs font-medium text-gray-500 dark:text-gray-400">Expected start</div>
					<div>{{ formatDate(task.exp_start_date) }}</div>
				</div>
				<div>
					<div class="text-xs font-medium text-gray-500 dark:text-gray-400">Expected end</div>
					<div>{{ formatDate(task.exp_end_date) }}</div>
				</div>
				<div>
					<div class="text-xs font-medium text-gray-500 dark:text-gray-400">Progress</div>
					<div>{{ task.progress ?? 0 }}%</div>
				</div>
				<div>
					<div class="text-xs font-medium text-gray-500 dark:text-gray-400">Project</div>
					<div>{{ task.project || "—" }}</div>
				</div>
				<div>
					<div class="text-xs font-medium text-gray-500 dark:text-gray-400">Department</div>
					<div>{{ task.department || "—" }}</div>
				</div>
				<div>
					<div class="text-xs font-medium text-gray-500 dark:text-gray-400">Owner</div>
					<div>{{ task.owner_name || task.owner || "—" }}</div>
				</div>
			</div>

			<div v-if="task.assignee_names?.length">
				<div class="mb-1 text-xs font-medium text-gray-500 dark:text-gray-400">Assignees</div>
				<div class="text-sm text-gray-800 dark:text-gray-200">{{ task.assignee_names.join(", ") }}</div>
			</div>

			<div v-if="task.description">
				<div class="mb-1 text-xs font-medium text-gray-500 dark:text-gray-400">Description</div>
				<div
					class="prose prose-sm dark:prose-invert max-w-none text-gray-800 dark:text-gray-200"
					v-html="task.description"
				/>
			</div>
		</div>
	</div>
</template>

<script setup>
import { formatDate } from "@spa/utils/datetime"

defineProps({
	task: { type: Object, required: true },
})

const emit = defineEmits(["close"])
</script>
