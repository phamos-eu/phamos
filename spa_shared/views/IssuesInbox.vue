<template>
	<div class="flex h-full min-h-0">
		<section
			v-if="!selectedName"
			class="order-1 flex min-w-0 flex-1 flex-col border-r border-outline-gray-2 bg-surface-white"
		>
			<div
				v-if="configError"
				class="flex flex-1 items-center justify-center px-6 text-center text-sm text-red-600 dark:text-red-400"
			>
				{{ configError }}
			</div>
			<div
				v-else-if="loading"
				class="flex flex-1 items-center justify-center text-sm text-ink-gray-5"
			>
				Loading…
			</div>
			<!-- Shared parent grid: toolbar always visible so filters can be cleared when empty. -->
			<div
				v-else
				:class="[ISSUE_LIST_FILTER_GRID, 'min-h-0 flex-1 content-start overflow-y-auto px-5']"
			>
				<div
					:class="[
						ISSUE_LIST_FILTER_SUBGRID,
						'sticky top-0 z-[1] border-b border-outline-gray-2 bg-surface-white py-3',
					]"
				>
					<FormControl
						v-model="search"
						type="text"
						size="sm"
						placeholder="Search…"
						class="w-full min-w-0"
					/>
					<div class="flex min-w-0 justify-center">
						<PriorityFilter
							v-model="priorityFilter"
							:priorities="formOptions.priorities || []"
						/>
					</div>
					<div class="flex min-w-0 justify-center">
						<StatusFilter v-model="statusFilter" />
					</div>
					<div class="flex min-w-0 justify-center">
						<ListSortSelector
							standalone
							v-model:sort-by="sortBy"
							v-model:sort-order="sortOrder"
							:options="createdSortOption"
						/>
					</div>
					<div class="flex min-w-0 justify-center">
						<ListSortSelector
							standalone
							v-model:sort-by="sortBy"
							v-model:sort-order="sortOrder"
							:options="modifiedSortOption"
						/>
					</div>
					<Button class="justify-self-end" variant="solid" @click="showCreate = true">
						New Issue
					</Button>
				</div>
				<IssueList
					v-if="filteredIssues.length"
					:issues="filteredIssues"
					:selected-name="selectedName"
					show-creator
					align-with-filters
					@select="openIssue"
				/>
				<div
					v-else
					class="col-span-6 flex flex-1 flex-col items-center justify-center gap-2 px-6 py-16 text-center"
				>
					<p class="font-medium text-ink-gray-9">No {{ spaConfig.label }} issues found</p>
					<p class="max-w-sm text-sm text-ink-gray-6">
						Try clearing search or status/priority filters, or select Closed to include closed issues.
					</p>
					<Button class="mt-2" @click="showCreate = true">Create an issue</Button>
				</div>
			</div>
		</section>

		<!-- Host first in DOM so Teleport target exists before IssueDetail mounts; order keeps it far right. -->
		<aside
			v-if="selectedName"
			id="issue-properties-host"
			class="order-4 flex w-72 flex-none flex-col overflow-hidden border-l border-outline-gray-2 bg-surface-white"
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
				@converted="onIssueConverted"
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
				:allow-create="selectedIssue.status !== 'Closed'"
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
import { ISSUE_LIST_FILTER_GRID, ISSUE_LIST_FILTER_SUBGRID } from "@spa/issueListColumns.js"
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
const createdSortOption = [{ label: "Created On", value: "creation" }]
const modifiedSortOption = [{ label: "Last Updated", value: "modified" }]
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
	} else {
		// Default: Closed hidden until the Closed status filter is activated
		list = list.filter((i) => i.status !== "Closed")
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
		// Include closed so StatusFilter can activate Closed client-side;
		// filteredIssues hides Closed by default until that pill is selected.
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

async function onIssueConverted(result) {
	if (result?.issue) selectedIssue.value = result.issue
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
