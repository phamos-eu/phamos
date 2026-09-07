<template>
	<div class="flex h-full min-h-0">
		<section
			v-if="!selectedName"
			class="order-1 flex min-w-0 flex-1 flex-col border-r border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900"
		>
			<div
				class="flex flex-wrap items-center justify-between gap-3 border-b border-gray-200 px-5 py-3 dark:border-gray-800"
			>
				<div class="flex flex-wrap items-center gap-x-8 gap-y-3">
					<FormControl v-model="search" type="text" size="sm" placeholder="Search…" class="w-44" />
					<StatusFilter v-model="statusFilter" />
					<PriorityFilter v-model="priorityFilter" :priorities="formOptions.priorities || []" />
					<ListSortSelector
						v-model:sort-by="sortBy"
						v-model:sort-order="sortOrder"
						:options="sortFieldOptions"
					/>
				</div>
				<Button variant="solid" @click="showCreate = true">New Issue</Button>
			</div>

			<div
				v-if="configError"
				class="flex flex-1 items-center justify-center px-6 text-center text-sm text-red-600 dark:text-red-400"
			>
				{{ configError }}
			</div>
			<div
				v-else-if="loading"
				class="flex flex-1 items-center justify-center text-sm text-gray-500 dark:text-gray-400"
			>
				Loading…
			</div>
			<template v-else-if="!filteredIssues.length">
				<div class="flex flex-1 flex-col items-center justify-center gap-2 px-6 text-center">
					<p class="font-medium text-gray-900 dark:text-gray-100">No {{ spaConfig.label }} issues found</p>
					<p class="max-w-sm text-sm text-gray-500 dark:text-gray-400">
						Issues linked to the {{ spaConfig.label }} department configured in phamos Settings will appear
						here.
					</p>
					<Button class="mt-2" @click="showCreate = true">Create an issue</Button>
				</div>
			</template>
			<!-- List-only inbox (Kanban/Calendar deferred). -->
			<IssueList
				v-else
				:issues="filteredIssues"
				:selected-name="selectedName"
				show-creator
				@select="openIssue"
			/>
		</section>

		<!-- Host first in DOM so Teleport target exists before IssueDetail mounts; order keeps it far right. -->
		<aside
			v-if="selectedName"
			id="issue-properties-host"
			class="order-4 flex w-72 flex-none flex-col overflow-hidden border-l border-gray-200 bg-gray-50/80 dark:border-gray-800 dark:bg-gray-950/40"
		/>

		<aside
			v-if="selectedName"
			class="order-2 flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden border-r border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900"
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
		</aside>

		<aside
			v-if="selectedName"
			class="order-3 flex min-w-0 flex-1 flex-col overflow-y-auto border-r border-gray-200 bg-white px-5 py-4 dark:border-gray-800 dark:bg-gray-900"
		>
			<div
				v-if="detailLoading && !selectedIssue"
				class="flex flex-1 items-center justify-center text-sm text-gray-500 dark:text-gray-400"
			>
				Loading checklists…
			</div>
			<LinkedChecklistsSection
				v-else-if="selectedIssue"
				:key="selectedIssue.name"
				document="Issue"
				:reference-record="selectedIssue.name"
				:reference-title="selectedIssue.subject"
			/>
		</aside>

		<CreateIssueDialog v-model="showCreate" :options="formOptions" @created="onCreated" />
	</div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { call } from "frappe-ui"
import IssueDetail from "@spa/components/IssueDetail.vue"
import IssueList from "@spa/components/IssueList.vue"
import CreateIssueDialog from "@spa/components/CreateIssueDialog.vue"
import LinkedChecklistsSection from "@spa/components/LinkedChecklistsSection.vue"
import ListSortSelector from "@spa/components/ListSortSelector.vue"
import PriorityFilter from "@spa/components/PriorityFilter.vue"
import StatusFilter from "@spa/components/StatusFilter.vue"
import spaConfig from "@/config"

const API = spaConfig.api

const route = useRoute()
const router = useRouter()

const search = ref("")
const priorityFilter = ref([])
const statusFilter = ref([])
// Desk Issue list defaults: sort_field=modified, sort_order=DESC
const sortBy = ref("modified")
const sortOrder = ref("desc")
const sortFieldOptions = [
	{ label: "Last Updated", value: "modified" },
	{ label: "Created On", value: "creation" },
]
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
	shortlist_users: [],
	departments: [],
	projects: [],
})

function compareIssues(a, b) {
	const field = sortBy.value === "creation" ? "creation" : "modified"
	const cmp = String(a[field] || "").localeCompare(String(b[field] || ""))
	return sortOrder.value === "desc" ? -cmp : cmp
}

function stripHtml(value) {
	return String(value || "")
		.replace(/<[^>]*>/g, " ")
		.replace(/\s+/g, " ")
		.trim()
}

function issueMatchesSearch(issue, q) {
	const fields = [
		issue.subject,
		issue.name,
		issue.priority,
		issue.issue_type,
		issue.owner_name,
		issue.description,
		issue.checklist_search,
		...(issue.assignee_names || []),
	]
	return fields
		.filter(Boolean)
		.some((v) => stripHtml(v).toLowerCase().includes(q))
}

const filteredIssues = computed(() => {
	const q = search.value.trim().toLowerCase()
	const priorities = priorityFilter.value
	const statuses = statusFilter.value
	let list = issues.value
	if (priorities.length) {
		const allowed = new Set(priorities)
		list = list.filter((i) => allowed.has(i.priority))
	}
	if (statuses.length) {
		const allowed = new Set(statuses)
		list = list.filter((i) => allowed.has(i.status))
	}
	if (q) {
		list = list.filter((i) => issueMatchesSearch(i, q))
	}
	return [...list].sort(compareIssues)
})

async function loadOptions() {
	try {
		formOptions.value = await call(`${API}.get_form_options`)
		configError.value = ""
	} catch (e) {
		configError.value = e?.messages?.[0] || e?.message || `Could not load ${spaConfig.label} settings`
	}
}

async function loadInbox() {
	if (configError.value) return
	loading.value = true
	try {
		// Always include closed so StatusFilter can toggle Closed client-side.
		issues.value = await call(`${API}.get_issues`, { include_closed: 1 })
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
	router.replace({ name: "IssuesList" })
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
