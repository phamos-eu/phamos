<template>
	<div class="flex h-full min-h-0">
		<section
			class="flex min-w-0 flex-col border-r border-outline-gray-2 bg-surface-white"
			:class="selectedName ? 'w-1/2 flex-none' : 'flex-1'"
		>
			<div v-if="configError" class="flex flex-1 items-center justify-center px-6 text-sm text-red-600">
				{{ configError }}
			</div>
			<div v-else-if="loading" class="flex flex-1 items-center justify-center text-sm text-ink-gray-5">
				Loading…
			</div>
			<div v-else :class="[listGridClass, 'min-h-0 flex-1 content-start overflow-y-auto px-5']">
				<div
					v-if="compact"
					class="sticky top-0 z-[1] col-span-4 space-y-2 border-b border-outline-gray-2 bg-surface-white py-3"
				>
					<FormControl
						v-model="search"
						type="text"
						size="sm"
						placeholder="Search title and checklist items…"
						class="w-full min-w-0"
					/>
					<div class="flex flex-wrap items-center justify-center gap-3">
						<StatusFilter v-model="statusFilter" :statuses="CHECKLIST_STATUSES" />
						<ListSortSelector
							standalone
							v-model:sort-by="sortBy"
							v-model:sort-order="sortOrder"
							:options="[{ label: 'Created On', value: 'creation' }]"
						/>
						<ChecklistOwnerFilter v-model="ownerFilter" :users="ownerOptions" />
					</div>
				</div>
				<div
					v-else
					:class="[
						CHECKLIST_LIST_FILTER_SUBGRID,
						'sticky top-0 z-[1] border-b border-outline-gray-2 bg-surface-white py-3',
					]"
				>
					<FormControl
						v-model="search"
						type="text"
						size="sm"
						placeholder="Search title and checklist items…"
						class="w-full min-w-0 max-w-xs"
					/>
					<div class="flex min-w-0 justify-center">
						<StatusFilter v-model="statusFilter" :statuses="CHECKLIST_STATUSES" />
					</div>
					<div class="flex min-w-0 justify-center">
						<ChecklistDoctypeFilter v-model="doctypeFilter" />
					</div>
					<div class="flex min-w-0 justify-center">
						<ListSortSelector
							standalone
							v-model:sort-by="sortBy"
							v-model:sort-order="sortOrder"
							:options="[{ label: 'Created On', value: 'creation' }]"
						/>
					</div>
					<div class="flex min-w-0 justify-center">
						<ListSortSelector
							standalone
							v-model:sort-by="sortBy"
							v-model:sort-order="sortOrder"
							:options="[{ label: 'Last Updated', value: 'modified' }]"
						/>
					</div>
					<div class="flex min-w-0 items-center justify-center">
						<ChecklistOwnerFilter v-model="ownerFilter" :users="ownerOptions" />
					</div>
					<Button class="justify-self-end" variant="solid" @click="showCreate = true">
						New Checklist
					</Button>
				</div>

				<div
					v-if="truncated"
					style="grid-column: 1 / -1"
					class="border-b border-outline-gray-2 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:bg-amber-950 dark:text-amber-200"
				>
					Showing the latest {{ rows.length }} checklists — narrow your filters to see older ones.
				</div>

				<div v-if="filtered.length" class="contents">
					<button
						v-for="row in filtered"
						:key="row.name"
						type="button"
						:class="[
							listSubgridClass,
							'border-b border-outline-gray-1 py-3 text-left hover:bg-surface-gray-2',
							row.name === selectedName
								? 'bg-surface-gray-2 shadow-[inset_3px_0_0_0_var(--outline-gray-4)]'
								: '',
						]"
						@click="openChecklist(row.name)"
					>
						<div class="grid min-w-0 grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 self-center">
							<div class="min-w-0">
								<div
									class="truncate text-sm font-semibold text-ink-gray-9"
									:title="row.title || row.name"
								>
									{{ row.title || row.name }}
								</div>
								<div
									class="mt-1.5 h-1.5 w-full max-w-[10rem] overflow-hidden rounded-full bg-surface-gray-2"
								>
									<div
										class="h-full rounded-full transition-[width]"
										:class="checklistProgressBarClass(row.status, row.completion_percentage)"
										:style="{ width: `${row.completion_percentage || 0}%` }"
									/>
								</div>
							</div>
							<div class="flex shrink-0 flex-col items-end space-y-0.5 text-right">
								<div class="text-xs font-semibold tabular-nums text-ink-gray-6">
									{{ row.name }}
								</div>
								<div class="text-xs tabular-nums text-ink-gray-6">
									{{ row.done_count || 0 }}/{{ row.total_count || 0 }}
								</div>
							</div>
						</div>

						<div class="flex min-w-0 justify-center self-center">
							<Badge
								class="whitespace-nowrap"
								:theme="checklistStatusTheme(row.status)"
								variant="subtle"
								size="sm"
								:label="row.status"
							/>
						</div>

						<div v-if="!compact" class="flex min-w-0 justify-center self-center">
							<a
								v-if="row.document && row.reference_record"
								:href="deskRecordUrl(row.document, row.reference_record)"
								target="_blank"
								rel="noopener noreferrer"
								class="inline-flex max-w-full items-center gap-1 rounded-md border border-outline-gray-2 px-2 py-1 text-xs leading-tight text-ink-gray-8 hover:bg-surface-gray-2"
								:title="`Open ${row.document} ${row.reference_record}`"
								@click.stop
							>
								<span class="flex min-w-0 flex-col items-center text-center">
									<span class="font-semibold">{{ row.document }}</span>
									<span class="truncate max-w-[5.5rem]">{{ row.reference_record }}</span>
								</span>
								<FeatherIcon name="external-link" class="h-3 w-3 shrink-0" />
							</a>
							<span v-else class="text-xs text-ink-gray-5">—</span>
						</div>

						<div class="min-w-0 space-y-0.5 self-center text-center text-xs text-ink-gray-6">
							<div>{{ formatRowDate(row.creation) }}</div>
							<div title="Checklist age">{{ formatAge(row.creation) }}</div>
						</div>

						<div v-if="!compact" class="min-w-0 self-center text-center text-xs text-ink-gray-6">
							{{ formatRowDate(row.modified) }}
						</div>

						<div class="flex min-w-0 justify-center self-center">
							<UserAvatar
								v-if="row.checklist_owner"
								:name="row.checklist_owner"
								:label="ownerLabel(row)"
								:image="row.checklist_owner_image"
								size="sm"
							/>
							<span v-else class="text-xs text-ink-gray-5">—</span>
						</div>

						<span v-if="!compact" aria-hidden="true" class="self-center" />
					</button>
				</div>

				<div
					v-else
					:class="[compact ? 'col-span-4' : 'col-span-7', 'flex min-h-72 flex-col items-center justify-center gap-2 text-center']"
				>
					<p class="font-medium text-ink-gray-9">No checklists found</p>
					<p class="text-sm text-ink-gray-5">Clear filters or create a checklist for an HR Issue or Task.</p>
					<Button class="mt-2" @click="showCreate = true">Create a checklist</Button>
				</div>
			</div>
		</section>

		<aside v-if="selectedName" class="flex w-1/2 min-w-0 flex-none flex-col overflow-y-auto bg-surface-white">
			<div v-if="detailLoading && !selected" class="flex flex-1 items-center justify-center text-sm text-ink-gray-5">
				Loading…
			</div>
			<ChecklistDetail
				v-else-if="selected"
				:checklist="selected"
				@close="closeChecklist"
				@updated="onUpdated"
			/>
		</aside>

		<CreateChecklistDialog
			v-model="showCreate"
			:create-method="`${API}.create_checklist`"
			:reference-query="`${API}.checklist_reference_query`"
			@created="onCreated"
		/>
	</div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { Badge, call } from "frappe-ui"
import ChecklistDetail from "@spa/components/ChecklistDetail.vue"
import ChecklistDoctypeFilter from "@spa/components/ChecklistDoctypeFilter.vue"
import ChecklistOwnerFilter from "@spa/components/ChecklistOwnerFilter.vue"
import CreateChecklistDialog from "@spa/components/CreateChecklistDialog.vue"
import ListSortSelector from "@spa/components/ListSortSelector.vue"
import StatusFilter from "@spa/components/StatusFilter.vue"
import UserAvatar from "@spa/components/UserAvatar.vue"
import {
	CHECKLIST_LIST_COMPACT_GRID,
	CHECKLIST_LIST_COMPACT_SUBGRID,
	CHECKLIST_LIST_FILTER_GRID,
	CHECKLIST_LIST_FILTER_SUBGRID,
	CHECKLIST_STATUSES,
	checklistProgressBarClass,
	checklistStatusTheme,
} from "@spa/checklistListColumns.js"
import { formatDate, formatIssueAge } from "@spa/utils/datetime.js"
import { deskRecordUrl } from "@spa/utils/deskUrl.js"
import spaConfig from "@/config"

const API = spaConfig.api
const CHECKLIST_API = "phamos.api.checklist_inbox"
const route = useRoute()
const router = useRouter()

const search = ref("")
const statusFilter = ref([])
const doctypeFilter = ref([])
const ownerFilter = ref([])
const sortBy = ref("modified")
const sortOrder = ref("desc")
const loading = ref(false)
const configError = ref("")
const rows = ref([])
const truncated = ref(false)
const showCreate = ref(false)
const selectedName = ref(null)
const selected = ref(null)
const detailLoading = ref(false)

const compact = computed(() => Boolean(selectedName.value))
const listGridClass = computed(() =>
	compact.value ? CHECKLIST_LIST_COMPACT_GRID : CHECKLIST_LIST_FILTER_GRID
)
const listSubgridClass = computed(() =>
	compact.value ? CHECKLIST_LIST_COMPACT_SUBGRID : CHECKLIST_LIST_FILTER_SUBGRID
)

function rowMatchesContext(row) {
	const q = search.value.trim().toLowerCase()
	const statuses = new Set(statusFilter.value)
	const doctypes = new Set(doctypeFilter.value)
	if (statuses.size ? !statuses.has(row.status) : row.status === "Completed") return false
	if (doctypes.size && !doctypes.has(row.document)) return false
	if (!q) return true
	return [row.title, row.name, row.status, row.document, row.reference_record, row.item_search]
		.filter(Boolean)
		.some((value) => String(value).toLowerCase().includes(q))
}

const contextRows = computed(() => rows.value.filter(rowMatchesContext))

const ownerOptions = computed(() => {
	const byName = new Map()
	for (const row of contextRows.value) {
		if (!row.checklist_owner || byName.has(row.checklist_owner)) continue
		byName.set(row.checklist_owner, {
			name: row.checklist_owner,
			full_name: row.checklist_owner_name || row.checklist_owner,
			user_image: row.checklist_owner_image || "",
		})
	}
	return [...byName.values()].sort((a, b) => a.full_name.localeCompare(b.full_name))
})

const filtered = computed(() => {
	const owners = new Set(ownerFilter.value)
	const list = owners.size
		? contextRows.value.filter((row) => owners.has(row.checklist_owner))
		: contextRows.value
	return [...list].sort((a, b) => {
		const left = a[sortBy.value]
		const right = b[sortBy.value]
		const result = String(left || "").localeCompare(String(right || ""))
		return sortOrder.value === "desc" ? -result : result
	})
})

watch(ownerOptions, (users) => {
	const available = new Set(users.map((user) => user.name))
	ownerFilter.value = ownerFilter.value.filter((name) => available.has(name))
})

function ownerLabel(row) {
	return row.checklist_owner_name || row.checklist_owner || "Unassigned"
}

function formatRowDate(value) {
	if (!value) return "—"
	return formatDate(String(value).slice(0, 10))
}

function formatAge(value) {
	if (!value) return "—"
	const age = formatIssueAge({ creation: value })
	if (!age || age === "—" || age === "Today") return age
	return `${age} old`
}

async function loadInbox() {
	loading.value = true
	configError.value = ""
	try {
		const data = await call(`${API}.get_checklists`, { include_completed: 1 })
		rows.value = data.items || []
		truncated.value = Boolean(data.truncated)
	} catch (e) {
		configError.value = e?.messages?.[0] || e?.message || "Could not load checklists"
	} finally {
		loading.value = false
	}
}

async function openChecklist(name) {
	selectedName.value = name
	if (route.params.name !== name) router.replace({ name: "ChecklistDetail", params: { name } })
	detailLoading.value = true
	try {
		selected.value = await call(`${CHECKLIST_API}.get_checklist`, { name })
	} finally {
		detailLoading.value = false
	}
}

function closeChecklist() {
	selectedName.value = null
	selected.value = null
	router.replace({ name: "Checklists" })
}

async function onUpdated(checklist) {
	selected.value = checklist
	await loadInbox()
}

async function onCreated(checklist) {
	showCreate.value = false
	await loadInbox()
	await openChecklist(checklist.name)
}

watch(
	() => route.params.name,
	(name) => {
		if (name && name !== selectedName.value) openChecklist(name)
		if (!name) {
			selectedName.value = null
			selected.value = null
		}
	}
)

onMounted(async () => {
	await loadInbox()
	if (route.params.name) await openChecklist(route.params.name)
})
</script>
