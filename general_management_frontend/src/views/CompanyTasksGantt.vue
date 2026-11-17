<template>
	<!-- "All departments" (#1948): top-level Tasks of every cockpit department, grouped by
	     department. Own Tasks edit as in TasksInbox.vue; other departments' Tasks are read-only. -->
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
				v-else-if="loading && !hasLoadedOnce"
				class="flex flex-1 items-center justify-center text-sm text-ink-gray-5"
			>
				Loading…
			</div>
			<TaskGantt
				v-else
				v-model:search="search"
				v-model:include-completed="includeCompleted"
				:tasks="rows"
				:selected-name="selectedName"
				:options="formOptions"
				@select="onSelect"
				@date-change="onGanttDateChange"
				@dependency-change="onGanttDependencyChange"
				@created="onTaskCreated"
			>
				<template #toolbar><slot name="toolbar" /></template>
			</TaskGantt>
		</section>

		<aside
			v-if="selectedName"
			class="flex w-96 flex-none flex-col overflow-hidden border-l border-outline-gray-2 bg-surface-white dark:bg-surface-gray-1"
		>
			<div
				v-if="detailLoading && !selectedTask && !readOnlyTask"
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
			<TaskReadOnlyDetail v-else-if="readOnlyTask" :task="readOnlyTask" @close="closeTask" />
		</aside>
	</div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { call, toast } from "frappe-ui"
import TaskDetail from "@spa/components/TaskDetail.vue"
import TaskGantt from "@spa/components/TaskGantt.vue"
import TaskReadOnlyDetail from "@spa/components/TaskReadOnlyDetail.vue"
import { buildCompanyRows, GROUP_ROW_PREFIX, isGroupRow } from "@spa/utils/companyGantt.js"
import { todayIsoInUserTz } from "@spa/utils/datetime"
import { useUserRealtime } from "@spa/composables/useUserRealtime.js"
import spaConfig from "@/config"

const API = spaConfig.api
// Collapsed departments, remembered per browser.
const COLLAPSED_KEY = "general-management-company-gantt-collapsed"

const route = useRoute()
const router = useRouter()

const includeCompleted = ref(false)
const search = ref("")
const loading = ref(false)
const hasLoadedOnce = ref(false)
const configError = ref("")
const groups = ref([])
const collapsed = ref(readCollapsed())
const selectedName = ref(null)
const selectedTask = ref(null) // own Task: editable TaskDetail
const readOnlyTask = ref(null) // another department's Task
const detailLoading = ref(false)
const formOptions = ref({ priorities: [], shortlist_users: [], projects: [] })

const rows = computed(() =>
	buildCompanyRows(groups.value, {
		collapsed: collapsed.value,
		search: search.value,
		fallbackDate: todayIsoInUserTz(),
	})
)

const ownNames = computed(
	() => new Set(groups.value.filter((g) => g.own).flatMap((g) => g.tasks.map((t) => t.name)))
)

function readCollapsed() {
	try {
		return JSON.parse(window.localStorage.getItem(COLLAPSED_KEY) || "[]")
	} catch {
		return []
	}
}

watch(collapsed, (value) => {
	try {
		window.localStorage.setItem(COLLAPSED_KEY, JSON.stringify(value))
	} catch {
		// Blocked storage: the groups just open expanded next time.
	}
})

function toggleGroup(department) {
	collapsed.value = collapsed.value.includes(department)
		? collapsed.value.filter((d) => d !== department)
		: [...collapsed.value, department]
}

async function loadOptions() {
	try {
		formOptions.value = await call(`${API}.get_form_options`)
		configError.value = formOptions.value[spaConfig.departmentField]
			? ""
			: `Configure ${spaConfig.label} Department in Cockpit Settings.`
	} catch (e) {
		configError.value = e?.messages?.[0] || e?.message || `Could not load ${spaConfig.label} settings`
	}
}

async function loadGroups() {
	if (configError.value) return
	loading.value = true
	try {
		groups.value = await call(`${API}.get_company_tasks`, {
			include_completed: includeCompleted.value ? 1 : 0,
		})
	} catch (e) {
		configError.value = e?.messages?.[0] || e?.message || "Could not load tasks"
	} finally {
		loading.value = false
		hasLoadedOnce.value = true
	}
}

function onSelect(name) {
	if (isGroupRow(name)) {
		toggleGroup(name.slice(GROUP_ROW_PREFIX.length))
		return
	}
	if (ownNames.value.has(name)) openOwnTask(name)
	else openReadOnlyTask(name)
}

async function openOwnTask(name) {
	selectedName.value = name
	readOnlyTask.value = null
	if (route.params.name !== name) router.replace({ name: "TaskDetail", params: { name } })
	detailLoading.value = true
	try {
		selectedTask.value = await call(`${API}.get_task`, { name })
	} catch (e) {
		// Not an own Task (e.g. a pasted link to another department's): no empty panel.
		closeTask()
		toast({ title: e?.messages?.[0] || "Could not load task", icon: "x-circle", iconClasses: "text-ink-red-4" })
	} finally {
		detailLoading.value = false
	}
}

// Other departments' Tasks stay out of the URL: /tasks/gantt/<name> is for own Tasks, which
// the "Own department" view opens too.
async function openReadOnlyTask(name) {
	selectedName.value = name
	selectedTask.value = null
	readOnlyTask.value = null
	if (route.params.name) router.replace({ name: "TasksGantt" })
	detailLoading.value = true
	try {
		readOnlyTask.value = await call(`${API}.get_company_task`, { name })
	} catch (e) {
		closeTask()
		toast({ title: e?.messages?.[0] || "Could not load task", icon: "x-circle", iconClasses: "text-ink-red-4" })
	} finally {
		detailLoading.value = false
	}
}

function closeTask() {
	selectedName.value = null
	selectedTask.value = null
	readOnlyTask.value = null
	if (route.params.name) router.replace({ name: "TasksGantt" })
}

async function onGanttDateChange({ name, exp_start_date, exp_end_date }) {
	try {
		const updated = await call(`${API}.update_task_dates`, { name, exp_start_date, exp_end_date })
		if (selectedName.value === name && selectedTask.value) selectedTask.value = updated
	} catch {
		// Refused (e.g. the Task left the department meanwhile): the reload puts the bar back.
	} finally {
		await loadGroups()
	}
}

async function onGanttDependencyChange({ name, depends_on }) {
	try {
		const updated = await call(`${API}.add_task_dependency`, { name, depends_on })
		await loadGroups()
		if (selectedName.value === name && selectedTask.value) selectedTask.value = updated
		toast({ title: "Dependency linked", icon: "check-circle", iconClasses: "text-ink-green-4" })
	} catch (e) {
		toast({
			title: e?.messages?.[0] || e?.message || "Could not link tasks",
			icon: "x-circle",
			iconClasses: "text-ink-red-4",
		})
	}
}

async function onTaskCreated(name) {
	await loadGroups()
	if (name) await openOwnTask(name)
}

async function onTaskUpdated(task) {
	if (task?.name === selectedName.value) selectedTask.value = task
	await loadGroups()
}

watch(includeCompleted, () => loadGroups())

watch(
	() => route.params.name,
	(name) => {
		if (name && name !== selectedName.value) openOwnTask(name)
	}
)

useUserRealtime("cockpit_todos_changed", loadGroups)

onMounted(async () => {
	await loadOptions()
	await loadGroups()
	// /tasks/gantt/<name> is for own Tasks only, also own subtasks and completed ones that the
	// company view doesn't list, so a link always opens the editable detail (as the route watcher).
	if (route.params.name) openOwnTask(route.params.name)
})
</script>
