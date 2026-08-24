<template>
	<div class="flex h-full min-h-0">
		<section
			class="flex min-w-0 flex-col border-r border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900"
			:class="selectedName ? 'w-1/3 flex-none' : 'flex-1'"
		>
			<div
				class="flex flex-wrap items-center justify-between gap-3 border-b border-gray-200 px-5 py-3 dark:border-gray-800"
			>
				<div class="flex flex-wrap items-center gap-3">
					<div class="inline-flex rounded-lg bg-gray-100 p-1 dark:bg-gray-800">
						<button
							v-for="tab in tabs"
							:key="tab.id"
							class="rounded-md px-3 py-1.5 text-sm font-medium transition"
							:class="
								view === tab.id
									? 'bg-white text-gray-900 shadow-sm dark:bg-gray-900 dark:text-gray-100'
									: 'text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-100'
							"
							@click="view = tab.id"
						>
							{{ tab.label }}
						</button>
					</div>
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
							@click="setLayout(opt.id)"
						>
							{{ opt.label }}
						</button>
					</div>
				</div>
				<div class="flex items-center gap-3">
					<label class="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
						<input v-model="includeClosed" type="checkbox" class="rounded border-gray-300 dark:border-gray-600" />
						Show closed
					</label>
					<input
						v-model="search"
						type="search"
						placeholder="Search…"
						class="h-8 w-44 rounded-md border border-gray-300 bg-white px-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
					/>
					<Button variant="solid" @click="showCreate = true">New Issue</Button>
				</div>
			</div>

			<div v-if="configError" class="flex flex-1 items-center justify-center px-6 text-center text-sm text-red-600 dark:text-red-400">
				{{ configError }}
			</div>
			<div v-else-if="loading" class="flex flex-1 items-center justify-center text-sm text-gray-500 dark:text-gray-400">
				Loading…
			</div>
			<template v-else-if="!filteredIssues.length && layout === 'list'">
				<div class="flex flex-1 flex-col items-center justify-center gap-2 px-6 text-center">
					<template v-if="view === 'assigned'">
						<p class="font-medium text-gray-900 dark:text-gray-100">Nothing assigned to you</p>
						<p class="max-w-sm text-sm text-gray-500 dark:text-gray-400">
							When someone assigns a Sales issue to you, it will show up here.
						</p>
					</template>
					<template v-else>
						<p class="font-medium text-gray-900 dark:text-gray-100">You have not created any issues yet</p>
						<p class="max-w-sm text-sm text-gray-500 dark:text-gray-400">
							Capture a Sales topic or follow-up with New Issue.
						</p>
						<Button class="mt-2" @click="showCreate = true">Create an issue</Button>
					</template>
				</div>
			</template>
			<IssueList
				v-else-if="layout === 'list'"
				:issues="filteredIssues"
				:selected-name="selectedName"
				:show-creator="view === 'assigned'"
				@select="openIssue"
			/>
			<IssueKanban
				v-else-if="layout === 'kanban'"
				:issues="filteredIssues"
				:selected-name="selectedName"
				@select="openIssue"
				@status-change="onKanbanStatusChange"
			/>
			<IssueCalendar
				v-else
				:issues="filteredIssues"
				:selected-name="selectedName"
				@select="openIssue"
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
					v-if="detailLoading && !selectedIssue"
					class="flex flex-1 items-center justify-center text-sm text-gray-500 dark:text-gray-400"
				>
					Loading…
				</div>
				<IssueDetail
					v-else-if="selectedIssue"
					:issue="selectedIssue"
					:options="formOptions"
					:api-prefix="API"
					@close="closeIssue"
					@updated="onIssueUpdated"
				/>
			</div>

			<div
				v-if="showChatColumn && selectedIssue"
				class="flex min-h-[280px] min-w-0 flex-1 flex-col border-t border-gray-200 dark:border-gray-800 md:min-h-0 md:border-l md:border-t-0"
			>
				<IssueChat
					:document-name="selectedIssue.name"
					linked-doctype="Issue"
					:chat-flags="chatFlags"
					:api-prefix="API"
				/>
			</div>
		</aside>

		<SalesCreateIssueDialog
			v-model="showCreate"
			:options="formOptions"
			@created="onCreated"
		/>
	</div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { call } from "frappe-ui"
import IssueCalendar from "@iown/components/IssueCalendar.vue"
import IssueChat from "@iown/components/IssueChat.vue"
import IssueDetail from "@iown/components/IssueDetail.vue"
import IssueKanban from "@iown/components/IssueKanban.vue"
import IssueList from "@iown/components/IssueList.vue"
import SalesCreateIssueDialog from "../components/SalesCreateIssueDialog.vue"

const API = "phamos.api.sales_spa"
const LAYOUT_KEY = "sales-spa-issues-layout"
const tabs = [
	{ id: "assigned", label: "Assigned to me" },
	{ id: "created", label: "Created by me" },
]
const layouts = [
	{ id: "list", label: "List" },
	{ id: "kanban", label: "Kanban" },
	{ id: "calendar", label: "Calendar" },
]

const route = useRoute()
const router = useRouter()

const view = ref("assigned")
const layout = ref(loadLayout())
const includeClosed = ref(false)
const search = ref("")
const loading = ref(false)
const configError = ref("")
const issues = ref([])
const showCreate = ref(false)
const selectedName = ref(null)
const selectedIssue = ref(null)
const detailLoading = ref(false)
const formOptions = ref({
	priorities: [],
	issue_types: [],
	users: [],
	departments: [],
	projects: [],
	sales_department: null,
	sales_standard_project: null,
	chat: { raven_installed: false, enabled: false, raven_unavailable: true },
})

const chatFlags = computed(() => formOptions.value.chat || {})
const showChatColumn = computed(() => !!chatFlags.value.raven_installed)

const filteredIssues = computed(() => {
	const q = search.value.trim().toLowerCase()
	if (!q) return issues.value
	return issues.value.filter((i) =>
		[i.subject, i.name, i.priority, i.issue_type, i.owner_name, ...(i.assignee_names || [])]
			.filter(Boolean)
			.some((v) => String(v).toLowerCase().includes(q))
	)
})

function loadLayout() {
	try {
		const stored = localStorage.getItem(LAYOUT_KEY)
		if (["list", "kanban", "calendar"].includes(stored)) return stored
	} catch (e) {
		/* ignore */
	}
	return "list"
}

function setLayout(id) {
	layout.value = id
	try {
		localStorage.setItem(LAYOUT_KEY, id)
	} catch (e) {
		/* ignore */
	}
}

async function loadOptions() {
	try {
		formOptions.value = await call(`${API}.get_form_options`)
		configError.value = ""
	} catch (e) {
		configError.value = e?.messages?.[0] || e?.message || "Could not load Sales settings"
	}
}

async function loadInbox() {
	if (configError.value) return
	loading.value = true
	try {
		issues.value = await call(`${API}.get_inbox`, {
			view: view.value,
			include_closed: includeClosed.value ? 1 : 0,
		})
	} catch (e) {
		configError.value = e?.messages?.[0] || e?.message || "Could not load issues"
	} finally {
		loading.value = false
	}
}

async function openIssue(name) {
	selectedName.value = name
	if (route.params.name !== name) {
		router.replace({ name: "IssueDetail", params: { name } })
	}
	detailLoading.value = true
	try {
		selectedIssue.value = await call(`${API}.get_issue`, { name })
	} finally {
		detailLoading.value = false
	}
}

function closeIssue() {
	selectedName.value = null
	selectedIssue.value = null
	router.replace({ name: "Issues" })
}

async function onCreated(issue) {
	showCreate.value = false
	await loadInbox()
	if (issue?.name) await openIssue(issue.name)
}

async function onIssueUpdated(issue) {
	selectedIssue.value = issue
	await loadInbox()
}

async function onKanbanStatusChange({ name, status }) {
	try {
		const updated = await call(`${API}.update_status`, { name, status })
		await loadInbox()
		if (selectedName.value === name) {
			selectedIssue.value = updated
		}
	} catch (e) {
		await loadInbox()
	}
}

watch([view, includeClosed], () => {
	loadInbox()
})

watch(
	() => route.params.name,
	(name) => {
		if (name && name !== selectedName.value) openIssue(name)
		if (!name) {
			selectedName.value = null
			selectedIssue.value = null
		}
	}
)

onMounted(async () => {
	await loadOptions()
	await loadInbox()
	if (route.params.name) {
		await openIssue(route.params.name)
	}
})
</script>
