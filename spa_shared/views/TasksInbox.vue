<template>
	<div class="flex h-full min-h-0">
		<section
			class="flex min-w-0 flex-1 flex-col border-r border-outline-gray-2 bg-surface-white dark:bg-surface-gray-1"
		>
			<div
				v-if="configError"
				class="flex flex-1 items-center justify-center px-6 text-center text-sm text-ink-red-4"
			>
				{{ configError }}
			</div>
			<div
				v-else-if="loading"
				class="flex flex-1 items-center justify-center text-sm text-ink-gray-5"
			>
				Loading…
			</div>
			<TaskGantt
				v-else
				v-model:search="search"
				v-model:include-completed="includeCompleted"
				:tasks="filteredTasks"
				:selected-name="selectedName"
				@select="openTask"
				@date-change="onGanttDateChange"
				@dependency-change="onGanttDependencyChange"
				@created="onTaskCreated"
			/>
		</section>

		<aside
			v-if="selectedName"
			class="flex w-96 flex-none flex-col overflow-hidden border-l border-outline-gray-2 bg-surface-white dark:bg-surface-gray-1"
		>
			<div
				v-if="detailLoading && !selectedTask"
				class="flex flex-1 items-center justify-center text-sm text-ink-gray-5"
			>
				Loading…
			</div>
			<TaskDetail
				v-else-if="selectedTask"
				:task="selectedTask"
				:options="formOptions"
				:api-prefix="API"
				@close="closeTask"
				@updated="onTaskUpdated"
			/>
		</aside>
	</div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { call, toast } from "frappe-ui"
import TaskDetail from "@spa/components/TaskDetail.vue"
import TaskGantt from "@spa/components/TaskGantt.vue"
import spaConfig from "@/config"

const API = spaConfig.api

const route = useRoute()
const router = useRouter()

const includeCompleted = ref(false)
const search = ref("")
const loading = ref(false)
const configError = ref("")
const tasks = ref([])
const selectedName = ref(null)
const selectedTask = ref(null)
const detailLoading = ref(false)
const formOptions = ref({
	priorities: [],
	shortlist_users: [],
	projects: [],
})

const filteredTasks = computed(() => {
	const q = search.value.trim().toLowerCase()
	if (!q) return tasks.value
	return tasks.value.filter((t) =>
		[t.subject, t.name, t.description, t.status, t.priority, ...(t.assignee_names || [])]
			.filter(Boolean)
			.some((v) => String(v).toLowerCase().includes(q))
	)
})

async function loadOptions() {
	try {
		formOptions.value = await call(`${API}.get_form_options`)
		const dept = formOptions.value[spaConfig.departmentField]
		configError.value = dept ? "" : `Configure ${spaConfig.label} Department in phamos Settings.`
	} catch (e) {
		configError.value = e?.messages?.[0] || e?.message || `Could not load ${spaConfig.label} settings`
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
	router.replace({ name: "TasksGantt" })
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
	if (name) await openTask(name)
}

async function onTaskUpdated(task) {
	selectedTask.value = task
	await loadTasks()
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
	await loadOptions()
	await loadTasks()
	if (route.params.name) await openTask(route.params.name)
})
</script>
