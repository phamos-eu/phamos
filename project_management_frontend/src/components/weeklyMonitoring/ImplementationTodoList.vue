<template>
	<div v-if="todos.length" class="overflow-hidden rounded-lg border border-gray-200 dark:border-gray-700">
		<table class="min-w-full divide-y divide-gray-200 text-sm dark:divide-gray-700">
			<thead class="bg-gray-50 dark:bg-gray-950">
				<tr>
					<th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-gray-500">Topic</th>
					<th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-gray-500">Due</th>
					<th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-gray-500">Assignee</th>
					<th v-if="!compact || closable" class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-gray-500"></th>
				</tr>
			</thead>
			<tbody class="divide-y divide-gray-100 dark:divide-gray-800">
				<tr v-for="todo in todos" :key="todo.name">
					<td class="px-3 py-2 text-gray-900 dark:text-gray-100">{{ todo.description }}</td>
					<td class="whitespace-nowrap px-3 py-2 text-gray-600 dark:text-gray-300">{{ formatDate(todo.date) }}</td>
					<td class="px-3 py-2 text-gray-600 dark:text-gray-300">{{ todo.assignee_name || "—" }}</td>
					<td v-if="!compact || closable" class="whitespace-nowrap px-3 py-2">
						<div class="flex items-center gap-2">
							<button
								v-if="closable"
								type="button"
								class="text-xs text-green-600 hover:text-green-800 disabled:opacity-50 dark:text-green-400 dark:hover:text-green-300"
								:disabled="closing === todo.name"
								@click="closeTodo(todo.name)"
							>
								{{ closing === todo.name ? "Closing…" : "Close" }}
							</button>
							<a
								v-if="!compact"
								:href="todo.desk_url"
								class="text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
								@click.stop
							>
								Desk
							</a>
						</div>
					</td>
				</tr>
			</tbody>
		</table>
	</div>
	<p v-else class="text-sm text-gray-500 dark:text-gray-400">No open to-dos for this implementation.</p>
</template>

<script setup>
import { ref } from "vue"
import { call, toast } from "frappe-ui"

const props = defineProps({
	todos: {
		type: Array,
		default: () => [],
	},
	compact: {
		type: Boolean,
		default: false,
	},
	closable: {
		type: Boolean,
		default: true,
	},
})

const emit = defineEmits(["closed"])

const API = "phamos.api.project_management_spa"
const closing = ref("")

function formatDate(value) {
	if (!value) return "—"
	try {
		return new Date(value).toLocaleDateString()
	} catch (e) {
		return value
	}
}

async function closeTodo(name) {
	closing.value = name
	try {
		await call(`${API}.close_implementation_todo`, { name })
		emit("closed", name)
		toast.success("To-do closed")
	} catch (e) {
		toast.error(e?.messages?.[0] || e?.message || "Could not close to-do")
	} finally {
		closing.value = ""
	}
}
</script>
