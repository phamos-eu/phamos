<template>
	<div class="flex h-full min-h-0 flex-col">
		<section v-if="!selectedName" class="flex h-full min-h-0 flex-col bg-surface-white">
			<div v-if="configError" class="flex flex-1 items-center justify-center px-6 text-center text-sm text-red-600">
				{{ configError }}
			</div>
			<div v-else-if="loading" class="flex flex-1 items-center justify-center text-sm text-ink-gray-5">
				{{ __("Loading…") }}
			</div>
			<template v-else>
				<!-- Opened from a figure of the lead overview (#1758): exactly the leads it counted. -->
				<div
					v-if="overviewActive"
					class="flex flex-shrink-0 flex-wrap items-center gap-2 border-b border-outline-gray-2 bg-surface-gray-1 px-5 py-2"
				>
					<RouterLink
						:to="overviewBackLink"
						class="mr-1 inline-flex items-center gap-1 text-sm text-ink-gray-7 hover:text-ink-gray-9"
					>
						<FeatherIcon name="arrow-left" class="h-4 w-4" />{{ __("Overview") }}
					</RouterLink>
					<span
						v-for="chip in filterChips"
						:key="chip.label"
						class="inline-flex items-center gap-1 rounded-full bg-surface-white px-2.5 py-1 text-xs text-ink-gray-8 ring-1 ring-outline-gray-2"
					>
						{{ chip.label }}
						<button
							type="button"
							class="rounded-full text-ink-gray-5 hover:text-ink-gray-9"
							:aria-label="__('Remove filter {0}', [chip.label])"
							@click="removeFilter(chip.keys)"
						>
							<FeatherIcon name="x" class="h-3.5 w-3.5" />
						</button>
					</span>
					<a :href="deskListUrl" class="ml-auto inline-flex items-center gap-1 text-sm text-ink-gray-7 hover:text-ink-gray-9">
						{{ __("Edit in Desk") }}<FeatherIcon name="external-link" class="h-3.5 w-3.5" />
					</a>
				</div>
				<div
					v-if="missingHint"
					class="flex-shrink-0 border-b border-outline-gray-2 bg-surface-amber-1 px-5 py-2 text-sm text-ink-amber-4"
				>
					{{ missingHint }}
				</div>
				<div class="flex flex-shrink-0 items-center justify-between border-b border-outline-gray-2 px-5 py-3">
					<p class="text-sm text-ink-gray-6">
						{{ filteredLeads.length === 1 ? __("1 lead") : __("{0} leads", [filteredLeads.length]) }}
					</p>
				</div>
				<div :class="[LEAD_LIST_FILTER_GRID, 'min-h-0 flex-1 content-start overflow-y-auto px-5']">
					<div
						:class="[
							LEAD_LIST_FILTER_SUBGRID,
							'sticky top-0 z-[1] border-b border-outline-gray-2 bg-surface-white py-3',
						]"
					>
						<FormControl v-model="search" type="text" size="sm" :placeholder="__('Search…')" class="w-full min-w-0 max-w-56" />
						<div class="flex min-w-0 justify-center">
							<!-- Nine statuses, several of them two words: they wrap inside
							     the column rather than running over their neighbours. -->
							<StatusFilter v-model="statusFilter" :statuses="statuses" :themes="LEAD_STATUS_THEMES" :label="leadStatusLabel" wrap />
						</div>
						<div class="flex min-w-0 justify-center">
							<ListSortSelector
								standalone
								v-model:sort-by="sortBy"
								v-model:sort-order="sortOrder"
								:options="followUpSortOption"
							/>
						</div>
						<div class="flex min-w-0 justify-center">
							<ListSortSelector
								standalone
								v-model:sort-by="sortBy"
								v-model:sort-order="sortOrder"
								:options="overviewActive ? createdSortOption : modifiedSortOption"
							/>
						</div>
						<div class="flex min-w-0 items-center justify-center pr-3">
							<AssigneeFilter
								v-model="ownerFilter"
								:users="ownerOptions"
								:aria-label="__('Filter by lead owner')"
							/>
						</div>
					</div>
					<div
						v-if="truncated"
						style="grid-column: 1 / -1"
						class="border-b border-outline-gray-2 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:bg-amber-950 dark:text-amber-200"
					>
						{{
							overviewActive
								? __("Showing the newest {0} leads. Narrow the filters to see the rest.", [leads.length])
								: __("Showing the first {0} leads by follow-up date. Leads with later follow-ups are not listed.", [leads.length])
						}}
					</div>
					<LeadList v-if="filteredLeads.length" :leads="filteredLeads" :show-created="overviewActive" @select="openLead" />
					<div
						v-else
						style="grid-column: 1 / -1"
						class="flex flex-1 flex-col items-center justify-center gap-1 px-6 py-16 text-center text-sm text-ink-gray-6"
					>
						{{ __("No leads found. Try clearing search or status filters.") }}
					</div>
				</div>
			</template>
		</section>

		<LeadDetail
			v-else
			:name="selectedName"
			@close="closeLead"
			@updated="onLeadUpdated"
		/>
	</div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { call, FeatherIcon } from "frappe-ui"
import {
	hasLeadFilters,
	leadDeskListUrl,
	leadFilterChips,
	leadFiltersFromQuery,
	NOT_SET,
	OVERVIEW_BACK_KEY,
} from "@spa/utils/leadFilters.js"
import { __ } from "@spa/utils/i18n.js"
import LeadDetail from "@/components/LeadDetail.vue"
import LeadList from "@/components/LeadList.vue"
import StatusFilter from "@spa/components/StatusFilter.vue"
import ListSortSelector from "@spa/components/ListSortSelector.vue"
import AssigneeFilter from "@/components/AssigneeFilter.vue"
import {
	LEAD_LIST_FILTER_GRID,
	LEAD_LIST_FILTER_SUBGRID,
	LEAD_STATUS_THEMES,
	leadStatusLabel,
} from "@/leadListColumns.js"

const API = "phamos.api.sales_leads"

// Terminal statuses hidden by default (mirrors IssuesInbox hiding Closed by default).
const DEFAULT_HIDDEN_STATUSES = new Set(["Converted", "Do Not Contact"])

const followUpSortOption = [{ label: __("Next Follow Up"), value: "custom_next_followup" }]
const modifiedSortOption = [{ label: __("Last Updated"), value: "modified" }]
const createdSortOption = [{ label: __("Created"), value: "creation" }]

const route = useRoute()
const router = useRouter()

const search = ref("")
const statusFilter = ref([])
const ownerFilter = ref([])
const sortBy = ref("custom_next_followup")
const sortOrder = ref("asc")
const loading = ref(false)
const configError = ref("")
const leads = ref([])
const statuses = ref([])
const truncated = ref(false)
const selectedName = ref(null)

// Filters from a figure of the lead overview, carried in the URL so the list can be shared and reloaded.
const overviewFilters = computed(() => leadFiltersFromQuery(route.query))
const overviewActive = computed(() => hasLeadFilters(overviewFilters.value))
const filterChips = computed(() => leadFilterChips(overviewFilters.value))
const deskListUrl = computed(() => leadDeskListUrl(overviewFilters.value))
// Back to the overview view the list was opened from, not the direction a drill-down row added.
const overviewBackLink = computed(() => {
	const from = route.query[OVERVIEW_BACK_KEY]
	return { name: "LeadsOverview", query: from === "Inbound" || from === "Outbound" ? { direction: from } : {} }
})
const missingHint = computed(() => {
	if (overviewFilters.value.direction === NOT_SET) {
		return __("These leads are not marked Inbound or Outbound yet. Open each one and choose, or set them in bulk via Edit in Desk.")
	}
	if (overviewFilters.value.source === NOT_SET) {
		return __("These leads have no source. Add one so the overview can tell where leads come from.")
	}
	return ""
})

function removeFilter(keys) {
	const query = { ...route.query }
	for (const key of keys) delete query[key]
	router.replace({ name: "LeadsFollowUps", query })
}

function stripHtml(value) {
	return String(value || "")
		.replace(/<[^>]*>/g, " ")
		.replace(/\s+/g, " ")
		.trim()
}

function leadMatchesSearch(lead, q) {
	const fields = [lead.name, lead.lead_name, lead.company_name, lead.email_id, lead.phone, lead.mobile_no, lead.owner_name]
	return fields.filter(Boolean).some((v) => stripHtml(String(v)).toLowerCase().includes(q))
}

function compareLeads(a, b) {
	if (sortBy.value === "modified" || sortBy.value === "creation") {
		const field = sortBy.value
		const cmp = String(a[field] || "").localeCompare(String(b[field] || ""))
		return sortOrder.value === "desc" ? -cmp : cmp
	}
	// custom_next_followup: leads with no date always sort first, regardless of order,
	// so reps can triage/clean them up — dated leads are then ordered by the toggle.
	const av = a.custom_next_followup
	const bv = b.custom_next_followup
	if (!av && !bv) return 0
	if (!av) return -1
	if (!bv) return 1
	const cmp = String(av).localeCompare(String(bv))
	return sortOrder.value === "desc" ? -cmp : cmp
}

/** Rows after search / status — used to derive the owner filter's options. */
const contextLeads = computed(() => {
	const q = search.value.trim().toLowerCase()
	const selected = statusFilter.value
	let list = leads.value
	if (selected.length) {
		const allowed = new Set(selected)
		list = list.filter((l) => allowed.has(l.status))
	} else if (!overviewActive.value) {
		// From the overview every status counts, Converted and Do Not Contact included.
		list = list.filter((l) => !DEFAULT_HIDDEN_STATUSES.has(l.status))
	}
	if (q) {
		list = list.filter((l) => leadMatchesSearch(l, q))
	}
	return list
})

const ownerOptions = computed(() => {
	const byName = new Map()
	for (const lead of contextLeads.value) {
		if (!lead.lead_owner || byName.has(lead.lead_owner)) continue
		byName.set(lead.lead_owner, {
			name: lead.lead_owner,
			full_name: lead.owner_name || lead.lead_owner,
			user_image: lead.owner_image || "",
		})
	}
	return [...byName.values()].sort((a, b) =>
		String(a.full_name || a.name).localeCompare(String(b.full_name || b.name))
	)
})

const filteredLeads = computed(() => {
	const owners = ownerFilter.value
	let list = contextLeads.value
	if (owners.length) {
		const allowed = new Set(owners)
		list = list.filter((l) => allowed.has(l.lead_owner))
	}
	return [...list].sort(compareLeads)
})

// Drop selected owners that are no longer among the visible options.
watch(ownerOptions, (users) => {
	const available = new Set(users.map((u) => u.name))
	const next = (ownerFilter.value || []).filter((id) => available.has(id))
	if (next.length !== ownerFilter.value.length) {
		ownerFilter.value = next
	}
})

let request = 0

async function loadLeads() {
	const mine = ++request
	loading.value = true
	try {
		const data = await call(`${API}.get_leads`, overviewFilters.value)
		if (mine !== request) return
		leads.value = data.items || []
		statuses.value = data.statuses || []
		truncated.value = Boolean(data.truncated)
		configError.value = ""
	} catch (e) {
		if (mine === request) configError.value = e?.messages?.[0] || e?.message || __("Could not load leads")
	} finally {
		if (mine === request) loading.value = false
	}
}

function openLead(name) {
	selectedName.value = name
	if (route.params.name !== name) {
		router.replace({ name: "LeadDetail", params: { name }, query: route.query })
	}
}

function closeLead() {
	selectedName.value = null
	router.replace({ name: "LeadsFollowUps", query: route.query })
	// A list from the overview shows what its figure counted; an edit (direction, source, status) can take a
	// lead out of it, so reload rather than keep a row that no longer belongs.
	if (overviewActive.value) loadLeads()
}

/** Newest first for an overview list, follow-up order for the daily one. */
function applyDefaultSort() {
	sortBy.value = overviewActive.value ? "creation" : "custom_next_followup"
	sortOrder.value = overviewActive.value ? "desc" : "asc"
}

watch(
	() => JSON.stringify(overviewFilters.value),
	(now, before) => {
		if (now === before) return
		applyDefaultSort()
		loadLeads()
	}
)

/** Same rule as the server: overdue only once the due date has passed. */
function isOverdue(date) {
	if (!date) return false
	const now = new Date()
	const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`
	return String(date).slice(0, 10) < today
}

function onLeadUpdated(updated) {
	const idx = leads.value.findIndex((l) => l.name === updated.name)
	if (idx !== -1) {
		leads.value[idx] = {
			...leads.value[idx],
			status: updated.status,
			custom_next_followup: updated.custom_next_followup,
			custom_status_comment: updated.custom_status_comment,
			company_name: updated.company_name,
			modified: updated.modified,
			lead_owner: updated.lead_owner,
			owner_name: updated.lead_owner_name,
			owner_image: updated.lead_owner_image,
			// Rescheduling an overdue lead is the core flow; the row must not
			// keep its red badge until a reload.
			overdue: isOverdue(updated.custom_next_followup),
		}
	}
}

watch(
	() => route.params.name,
	(name) => {
		if (name && name !== selectedName.value) openLead(name)
		if (!name) {
			selectedName.value = null
		}
	}
)

onMounted(async () => {
	applyDefaultSort()
	await loadLeads()
	if (route.params.name) {
		openLead(route.params.name)
	}
})
</script>
