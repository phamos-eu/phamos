<template>
	<div class="flex h-full min-h-0">
		<section
			class="flex min-w-0 flex-col border-r border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900"
			:class="selectedName ? 'w-1/3 flex-none' : 'flex-1'"
		>
			<div
				class="flex flex-wrap items-center justify-between gap-3 border-b border-gray-200 px-5 py-3 dark:border-gray-800"
			>
				<div class="inline-flex rounded-lg border border-gray-200 p-0.5 dark:border-gray-700">
					<button
						v-for="opt in layouts"
						:key="opt.id"
						class="rounded-md px-2.5 py-1 text-xs font-medium transition"
						:class="
							layout === opt.id
								? 'bg-gray-900 text-white dark:bg-gray-100 dark:text-gray-900'
								: 'text-gray-600 hover:bg-gray-50 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-100'
						"
						@click="layout = opt.id"
					>
						{{ opt.label }}
					</button>
				</div>
				<div v-if="layout !== 'gantt'" class="flex items-center gap-3">
					<label class="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
						<input v-model="includeCompleted" type="checkbox" class="rounded border-gray-300 dark:border-gray-600" />
						Show completed
					</label>
					<input
						v-model="search"
						type="search"
						placeholder="Search…"
						class="h-8 w-44 rounded-md border border-gray-300 bg-white px-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
					/>
				</div>
			</div>

			<div v-if="configError" class="flex flex-1 items-center justify-center px-6 text-center text-sm text-red-600 dark:text-red-400">
				{{ configError }}
			</div>
			<div v-else-if="loading" class="flex flex-1 items-center justify-center text-sm text-gray-500 dark:text-gray-400">
				Loading…
			</div>
			<template v-else-if="!filteredTasks.length && layout !== 'gantt'">
				<div class="flex flex-1 flex-col items-center justify-center gap-2 px-6 text-center">
					<p class="font-medium text-gray-900 dark:text-gray-100">No Accounting tasks found</p>
					<p class="max-w-sm text-sm text-gray-500 dark:text-gray-400">
						Tasks linked to the Accounting department configured in phamos Settings will appear here.
					</p>
				</div>
			</template>
			<TaskGantt
				v-else-if="layout === 'gantt'"
				v-model:search="search"
				v-model:include-completed="includeCompleted"
				:tasks="filteredTasks"
				:selected-name="selectedName"
				@select="openTask"
				@date-change="onGanttDateChange"
				@dependency-change="onGanttDependencyChange"
				@created="onTaskCreated"
			/>
			<TaskKanban
				v-else
				:tasks="filteredTasks"
				:selected-name="selectedName"
				@select="openTask"
				@status-change="onKanbanStatusChange"
			/>
		</section>

		<aside
			v-if="selectedName"
			class="flex w-2/3 min-w-0 flex-none flex-col bg-white dark:bg-gray-900 md:flex-row"
		>
			<div
				class="flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto"
				:class="{ 'md:border-r md:border-gray-200 dark:md:border-gray-800': showChatColumn }"
			>
				<div
					v-if="detailLoading && !selectedTask"
					class="flex flex-1 items-center justify-center text-sm text-gray-500 dark:text-gray-400"
				>
					Loading…
				</div>
				<TaskDetail v-else-if="selectedTask" :task="selectedTask" @close="closeTask" />
			</div>

			<div
				v-if="showChatColumn && selectedTask"
				class="flex min-h-[280px] min-w-0 flex-1 flex-col border-t border-gray-200 dark:border-gray-800 md:min-h-0 md:border-l md:border-t-0"
			>
				<IssueChat
					:document-name="selectedTask.name"
					linked-doctype="Task"
					:chat-flags="chatFlags"
					:api-prefix="API"
				/>
			</div>
		</aside>
	</div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { call, toast } from "frappe-ui"
import IssueChat from "@iown/components/IssueChat.vue"
import TaskDetail from "@spa/components/TaskDetail.vue"
import TaskGantt from "@spa/components/TaskGantt.vue"
import TaskKanban from "@spa/components/TaskKanban.vue"

const API = "phamos.api.accounting_spa"
const layouts = [
	{ id: "gantt", label: "Gantt" },
	{ id: "kanban", label: "Kanban" },
]

const route = useRoute()
const router = useRouter()

const layout = ref("gantt")
const includeCompleted = ref(false)
const search = ref("")
const loading = ref(false)
const configError = ref("")
const tasks = ref([])
const selectedName = ref(null)
const selectedTask = ref(null)
const detailLoading = ref(false)
const chatFlags = ref({ raven_installed: false, enabled: false, raven_unavailable: true })

const showChatColumn = computed(() => !!chatFlags.value.raven_installed)

const filteredTasks = computed(() => {
	const q = search.value.trim().toLowerCase()
	if (!q) return tasks.value
	return tasks.value.filter((t) =>
		[t.subject, t.name, t.description, t.status, t.priority, ...(t.assignee_names || [])]
			.filter(Boolean)
			.some((v) => String(v).toLowerCase().includes(q))
	)
})

async function loadSettings() {
	try {
		const settings = await call(`${API}.get_accounting_settings`)
		chatFlags.value = settings.chat || chatFlags.value
		configError.value = settings.accounting_department ? "" : "Configure Accounting Department in phamos Settings."
	} catch (e) {
		configError.value = e?.messages?.[0] || e?.message || "Could not load Accounting settings"
	}
}

async function loadTasks() {
	if (configError.value) return
	loading.value = true
	try {
		tasks.value = await call(`${API}.get_tasks`, {
			include_completed: includeCompleted.value ? 1 : 0,
		})
	} catch (e) {
		configError.value = e?.messages?.[0] || e?.message || "Could not load tasks"
	} finally {
		loading.value = false
	}
}

async function openTask(name) {
	selectedName.value = name
	if (route.params.name !== name) {
		router.replace({ name: "TaskDetail", params: { name } })
	}
	detailLoading.value = true
	try {
		selectedTask.value = await call(`${API}.get_task`, { name })
	} finally {
		detailLoading.value = false
	}
}

function closeTask() {
	selectedName.value = null
	selectedTask.value = null
	router.replace({ name: "Tasks" })
}

async function onKanbanStatusChange({ name, status }) {
	try {
		const updated = await call(`${API}.update_task_status`, { name, status })
		await loadTasks()
		if (selectedName.value === name) selectedTask.value = updated
	} catch (e) {
		await loadTasks()
	}
}

async function onGanttDateChange({ name, exp_start_date, exp_end_date }) {
	try {
		const updated = await call(`${API}.update_task_dates`, {
			name,
			exp_start_date,
			exp_end_date,
		})
		await loadTasks()
		if (selectedName.value === name) selectedTask.value = updated
	} catch (e) {
		await loadTasks()
	}
}

async function onGanttDependencyChange({ name, depends_on }) {
	try {
		const updated = await call(`${API}.add_task_dependency`, { name, depends_on })
		await loadTasks()
		if (selectedName.value === name) selectedTask.value = updated
		toast.success("Dependency linked")
	} catch (e) {
		toast.error(e?.messages?.[0] || e?.message || "Could not link tasks")
	}
}

async function onTaskCreated(name) {
	await loadTasks()
	await openTask(name)
}

watch(includeCompleted, () => {
	loadTasks()
})

watch(
	() => route.params.name,
	(name) => {
		if (name && name !== selectedName.value) openTask(name)
		if (!name) {
			selectedName.value = null
			selectedTask.value = null
		}
	}
)

onMounted(async () => {
	await loadSettings()
	await loadTasks()
	if (route.params.name) await openTask(route.params.name)
})
</script>
