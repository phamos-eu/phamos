<template>
	<div class="flex h-full min-h-0">
		<section
			class="flex min-w-0 flex-col border-r border-outline-gray-2 bg-surface-white"
			:class="selectedName ? 'w-96 flex-none' : 'flex-1'"
		>
			<div v-if="configError" class="flex flex-1 items-center justify-center px-6 text-center text-sm text-red-600">
				{{ configError }}
			</div>
			<div v-else-if="loading" class="flex flex-1 items-center justify-center text-sm text-ink-gray-5">
				Loading…
			</div>
			<template v-else>
				<div class="sticky top-0 z-[1] flex flex-col gap-2 border-b border-outline-gray-2 bg-surface-white p-3">
					<FormControl v-model="search" type="text" size="sm" placeholder="Search…" class="w-full" />
					<StatusFilter v-model="statusFilter" :statuses="statuses" />
					<ListSortSelector
						v-model:sort-by="sortBy"
						v-model:sort-order="sortOrder"
						:options="sortOptions"
					/>
				</div>
				<LeadList
					:leads="filteredLeads"
					:selected-name="selectedName"
					:compact="!!selectedName"
					@select="openLead"
				/>
			</template>
		</section>

		<template v-if="selectedName">
			<!-- Host first in DOM so Teleport target exists before LeadDetail mounts -->
			<aside
				id="lead-properties-host"
				class="order-3 flex w-72 flex-none flex-col overflow-hidden border-l border-outline-gray-2 bg-surface-white"
			/>
			<aside class="order-2 flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden border-r border-outline-gray-2 bg-surface-white">
				<div v-if="detailLoading && !selectedLead" class="flex flex-1 items-center justify-center text-sm text-ink-gray-5">
					Loading…
				</div>
				<LeadDetail v-else-if="selectedLead" :lead="selectedLead" @updated="onLeadUpdated" />
			</aside>
		</template>
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

const API = "phamos.api.sales_leads"

// Terminal statuses hidden by default (mirrors IssuesInbox hiding Closed by default).
const DEFAULT_HIDDEN_STATUSES = new Set(["Converted", "Do Not Contact"])

const sortOptions = [
	{ label: "Next Follow Up", value: "custom_next_followup" },
	{ label: "Last Updated", value: "modified" },
]

const route = useRoute()
const router = useRouter()

const search = ref("")
const statusFilter = ref([])
const sortBy = ref("custom_next_followup")
const sortOrder = ref("asc")
const loading = ref(false)
const configError = ref("")
const leads = ref([])
const statuses = ref([])
const truncated = ref(false)
const selectedName = ref(null)
const selectedLead = ref(null)
const detailLoading = ref(false)

function stripHtml(value) {
	return String(value || "")
		.replace(/<[^>]*>/g, " ")
		.replace(/\s+/g, " ")
		.trim()
}

function leadMatchesSearch(lead, q) {
	const fields = [
		lead.name,
		lead.lead_name,
		lead.company_name,
		lead.email_id,
		lead.phone,
		lead.mobile_no,
		lead.owner_name,
	]
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

const filteredLeads = computed(() => {
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
	return [...list].sort(compareLeads)
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

async function openLead(name) {
	selectedName.value = name
	if (route.params.name !== name) {
		router.replace({ name: "LeadDetail", params: { name } })
	}
	detailLoading.value = true
	try {
		selectedLead.value = await call(`${API}.get_lead`, { name })
	} finally {
		detailLoading.value = false
	}
}

function onLeadUpdated(updated) {
	selectedLead.value = updated
	const idx = leads.value.findIndex((l) => l.name === updated.name)
	if (idx !== -1) {
		leads.value[idx] = {
			...leads.value[idx],
			status: updated.status,
			custom_next_followup: updated.custom_next_followup,
		}
	}
}

watch(
	() => route.params.name,
	(name) => {
		if (name && name !== selectedName.value) openLead(name)
		if (!name) {
			selectedName.value = null
			selectedLead.value = null
		}
	}
)

onMounted(async () => {
	await loadLeads()
	if (route.params.name) {
		await openLead(route.params.name)
	}
})
</script>
