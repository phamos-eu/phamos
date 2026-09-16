<template>
	<div class="flex h-full min-h-0 flex-col">
		<section v-if="!selectedName" class="flex h-full min-h-0 flex-col bg-surface-white">
			<div v-if="configError" class="flex flex-1 items-center justify-center px-6 text-center text-sm text-red-600">
				{{ configError }}
			</div>
			<div v-else-if="loading" class="flex flex-1 items-center justify-center text-sm text-ink-gray-5">
				Loading…
			</div>
			<template v-else>
				<div class="flex flex-shrink-0 items-center justify-between border-b border-outline-gray-2 px-5 py-3">
					<p class="text-sm text-ink-gray-6">
						{{ filteredLeads.length }} lead{{ filteredLeads.length === 1 ? "" : "s" }}
					</p>
				</div>
				<div :class="[LEAD_LIST_FILTER_GRID, 'min-h-0 flex-1 content-start overflow-y-auto px-5']">
					<div
						:class="[
							LEAD_LIST_FILTER_SUBGRID,
							'sticky top-0 z-[1] border-b border-outline-gray-2 bg-surface-white py-3',
						]"
					>
						<FormControl v-model="search" type="text" size="sm" placeholder="Search…" class="w-full min-w-0 max-w-56" />
						<div class="flex min-w-0 justify-center">
							<!-- Nine statuses, several of them two words: they wrap inside
							     the column rather than running over their neighbours. -->
							<StatusFilter v-model="statusFilter" :statuses="statuses" :themes="LEAD_STATUS_THEMES" wrap />
						</div>
						<div class="flex min-w-0 justify-center">
							<ListSortSelector
								standalone
								v-model:sort-by="sortBy"
								v-model:sort-order="sortOrder"
								:options="followUpSortOption"
							/>
						</div>
						<!-- Next step has no sort or filter of its own; the cell keeps the
						     toolbar aligned with the rows. -->
						<div class="flex min-w-0 justify-center text-xs text-ink-gray-5">Next Step</div>
						<div class="flex min-w-0 justify-center">
							<ListSortSelector
								standalone
								v-model:sort-by="sortBy"
								v-model:sort-order="sortOrder"
								:options="modifiedSortOption"
							/>
						</div>
						<div class="flex min-w-0 items-center justify-center pr-3">
							<AssigneeFilter
								v-model="ownerFilter"
								:users="ownerOptions"
								aria-label="Filter by lead owner"
							/>
						</div>
					</div>
					<div
						v-if="truncated"
						style="grid-column: 1 / -1"
						class="border-b border-outline-gray-2 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:bg-amber-950 dark:text-amber-200"
					>
						Showing the latest {{ leads.length }} leads — narrow your filters to see older ones.
					</div>
					<LeadList v-if="filteredLeads.length" :leads="filteredLeads" @select="openLead" />
					<div
						v-else
						style="grid-column: 1 / -1"
						class="flex flex-1 flex-col items-center justify-center gap-1 px-6 py-16 text-center text-sm text-ink-gray-6"
					>
						No leads found. Try clearing search or status filters.
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
import { call } from "frappe-ui"
import LeadDetail from "@/components/LeadDetail.vue"
import LeadList from "@/components/LeadList.vue"
import StatusFilter from "@spa/components/StatusFilter.vue"
import ListSortSelector from "@spa/components/ListSortSelector.vue"
import AssigneeFilter from "@spa/components/AssigneeFilter.vue"
import {
	LEAD_LIST_FILTER_GRID,
	LEAD_LIST_FILTER_SUBGRID,
	LEAD_STATUS_THEMES,
} from "@/leadListColumns.js"

const API = "phamos.api.sales_leads"

// Terminal statuses hidden by default (mirrors IssuesInbox hiding Closed by default).
const DEFAULT_HIDDEN_STATUSES = new Set(["Converted", "Do Not Contact"])

const followUpSortOption = [{ label: "Next Follow Up", value: "custom_next_followup" }]
const modifiedSortOption = [{ label: "Last Updated", value: "modified" }]

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
	if (sortBy.value === "modified") {
		const cmp = String(a.modified || "").localeCompare(String(b.modified || ""))
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
	} else {
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

async function loadLeads() {
	loading.value = true
	try {
		const data = await call(`${API}.get_leads`)
		leads.value = data.items || []
		statuses.value = data.statuses || []
		truncated.value = Boolean(data.truncated)
		configError.value = ""
	} catch (e) {
		configError.value = e?.messages?.[0] || e?.message || "Could not load leads"
	} finally {
		loading.value = false
	}
}

function openLead(name) {
	selectedName.value = name
	if (route.params.name !== name) {
		router.replace({ name: "LeadDetail", params: { name } })
	}
}

function closeLead() {
	selectedName.value = null
	router.replace({ name: "LeadsFollowUps" })
}

function onLeadUpdated(updated) {
	const idx = leads.value.findIndex((l) => l.name === updated.name)
	if (idx !== -1) {
		leads.value[idx] = {
			...leads.value[idx],
			status: updated.status,
			custom_next_followup: updated.custom_next_followup,
			lead_owner: updated.lead_owner,
			owner_name: updated.lead_owner_name,
			owner_image: updated.lead_owner_image,
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
	await loadLeads()
	if (route.params.name) {
		openLead(route.params.name)
	}
})
</script>
