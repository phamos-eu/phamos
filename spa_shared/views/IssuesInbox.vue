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
						<ListSortSelector
							standalone
							v-model:sort-by="sortBy"
							v-model:sort-order="sortOrder"
							:options="chatSortOption"
							@clear="resetSort"
						/>
					</div>
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
					<ChecklistOwnerFilter
						v-model="assigneeFilter"
						:users="assigneeOptions"
						:label="__('Filter by assignee')"
						overlap
					/>
					<Button class="justify-self-end" variant="solid" @click="showCreate = true">
						New Issue
					</Button>
				</div>
				<div
					v-if="truncated"
					style="grid-column: 1 / -1"
					class="border-b border-outline-gray-2 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:bg-amber-950 dark:text-amber-200"
				>
					Showing the latest {{ issues.length }} issues — narrow your filters to see older ones.
				</div>
				<IssueList
					v-if="filteredIssues.length"
					:issues="filteredIssues"
					:chat-states="chatStates"
					:selected-name="selectedName"
					show-creator
					align-with-filters
					@select="openIssue"
				/>
				<div
					v-else
					class="col-span-8 flex flex-1 flex-col items-center justify-center gap-2 px-6 py-16 text-center"
				>
					<p class="font-medium text-ink-gray-9">No {{ spaConfig.label }} issues found</p>
					<p class="max-w-sm text-sm text-ink-gray-6">
						Try clearing search or status/priority filters, or select Closed to include closed issues.
					</p>
					<Button class="mt-2" @click="showCreate = true">Create an issue</Button>
				</div>
			</div>
		</section>

		<!-- The open Issue as tiles (#1915): description, chat, checklists, Phriend report and
		     properties are panels the user arranges; IssueDetail keeps the Issue's state and lays
		     the description and properties into their panels. -->
		<div v-if="selectedName" class="order-2 flex min-h-0 min-w-0 flex-1">
			<div
				v-if="detailLoading && !selectedIssue"
				class="flex flex-1 items-center justify-center text-sm text-gray-500 dark:text-gray-400"
			>
				Loading…
			</div>
			<template v-else-if="selectedIssue">
				<PanelLayout doctype="Issue" :record="selectedIssue" />
				<IssueDetail
					:issue="selectedIssue"
					:options="formOptions"
					:api-prefix="API"
					@close="closeIssue"
					@updated="onIssueUpdated"
					@converted="onIssueConverted"
				/>
			</template>
		</div>

		<CreateIssueDialog v-model="showCreate" :options="formOptions" @created="onCreated" />
	</div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { call } from "frappe-ui"
import IssueDetail from "@spa/components/IssueDetail.vue"
import { useIssueChatStates } from "@spa/composables/useIssueChatStates.js"
import { compareChatStates } from "@spa/utils/chatUnread.js"
import { prewarmRavenFrame } from "@spa/utils/ravenFrame.js"
import { useUserRealtime } from "@spa/composables/useUserRealtime.js"
import { __ } from "@spa/utils/i18n.js"
import IssueList from "@spa/components/IssueList.vue"
import ChecklistOwnerFilter from "@spa/components/ChecklistOwnerFilter.vue"
import CreateIssueDialog from "@spa/components/CreateIssueDialog.vue"
import PanelLayout from "@spa/panels/PanelLayout.vue"
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
// Most urgent chats first; a second click goes back to the default sort (#1796).
const chatSortOption = [{ label: __("Chat"), value: "chat", oneWay: true }]

function resetSort() {
	sortBy.value = "modified"
	sortOrder.value = "desc"
}
const loading = ref(false)
const configError = ref("")
const issues = ref([])
const truncated = ref(false)
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
	if (sortBy.value === "chat") {
		// Most urgent first (#1796): mentions, unread, read chats, none; same chat state: last updated first.
		const cmp = compareChatStates(chatStates.value[a.name], chatStates.value[b.name])
		if (cmp) return -cmp
		return String(b.modified || "").localeCompare(String(a.modified || ""))
	}
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

// Everyone assigned to a loaded Issue, for the avatar filter above the Assigned column.
const assigneeFilter = ref([])
const assigneeOptions = computed(() => {
	const byName = new Map()
	for (const issue of issues.value) {
		;(issue.assignees || []).forEach((name, i) => {
			if (!name || byName.has(name)) return
			byName.set(name, {
				name,
				full_name: (issue.assignee_names || [])[i] || name,
				user_image: (issue.assignee_images || [])[i] || "",
			})
		})
	}
	return [...byName.values()].sort((a, b) => a.full_name.localeCompare(b.full_name))
})

const visibleIssues = computed(() => {
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
	if (assigneeFilter.value.length) {
		const wanted = new Set(assigneeFilter.value)
		list = list.filter((i) => (i.assignees || []).some((u) => wanted.has(u)))
	}
	if (q) {
		list = list.filter((i) => issueMatchesSearch(i, q))
	}
	return list
})
// Loaded for the unsorted rows, so sorting by chat does not reload the states it sorts by.
const chatStates = useIssueChatStates(visibleIssues)
// Boot Raven while the list sits idle, so the first chat opens as fast as the next ones (#1796).
// Only when the list has chats: then the chat is on and the user is in Raven.
const stopPrewarm = watch(chatStates, (states) => {
	if (!Object.keys(states || {}).length) return
	stopPrewarm()
	const idle = window.requestIdleCallback || ((fn) => setTimeout(fn, 1500))
	idle(() => prewarmRavenFrame(), { timeout: 3000 })
})
const filteredIssues = computed(() => [...visibleIssues.value].sort(compareIssues))

async function loadOptions() {
	try {
		formOptions.value = await call(`${API}.get_form_options`)
		configError.value = ""
	} catch (e) {
		configError.value = e?.messages?.[0] || e?.message || `Could not load ${spaConfig.label} settings`
	}
}

/** `quiet`: a background refresh keeps the list on screen and ignores errors. */
async function loadInbox({ quiet = false } = {}) {
	if (configError.value) return
	if (!quiet) loading.value = true
	try {
		// Include closed so StatusFilter can activate Closed client-side;
		// filteredIssues hides Closed by default until that pill is selected.
		const data = await call(`${API}.get_issues`, { include_closed: 1 })
		issues.value = data.items || []
		truncated.value = Boolean(data.truncated)
	} catch (e) {
		if (!quiet) configError.value = e?.messages?.[0] || e?.message || "Could not load issues"
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
	// Saves finish after the user may have opened another record; a late
	// response must not switch the detail view back.
	if (issue?.name === selectedName.value) selectedIssue.value = issue
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

// Someone assigned or unassigned the user elsewhere (another cockpit, Desk): their ToDos
// changed, so Issues may have joined or left this list.
useUserRealtime("cockpit_todos_changed", () => loadInbox({ quiet: true }))

onMounted(async () => {
	await loadOptions()
	await loadInbox()
	if (route.params.name) {
		await openIssue(route.params.name)
	}
})
</script>
