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
			<div
				v-else
				:class="[MIS_LIST_FILTER_GRID, 'min-h-0 flex-1 content-start overflow-y-auto px-5']"
			>
				<div
					:class="[
						MIS_LIST_FILTER_SUBGRID,
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
					<FormControl
						v-model="implementationFilter"
						type="select"
						size="sm"
						:options="implementationOptions"
						class="w-full min-w-0"
					/>
					<FormControl
						v-model="monthFilter"
						type="select"
						size="sm"
						:options="monthOptions"
						class="w-full min-w-0"
					/>
					<div class="flex min-w-0 justify-center">
						<MisStatusFilter v-model="statusFilter" :statuses="MIS_STATUSES" />
					</div>
					<div class="flex min-w-0 justify-center">
						<ListSortSelector
							standalone
							v-model:sort-by="sortBy"
							v-model:sort-order="sortOrder"
							:options="totalHoursSortOption"
						/>
					</div>
					<div class="flex min-w-0 justify-center">
						<ListSortSelector
							standalone
							v-model:sort-by="sortBy"
							v-model:sort-order="sortOrder"
							:options="billableHoursSortOption"
						/>
					</div>
					<div class="flex min-w-0 justify-center">
						<ListSortSelector
							standalone
							v-model:sort-by="sortBy"
							v-model:sort-order="sortOrder"
							:options="deltaSortOption"
						/>
					</div>
					<div class="flex min-w-0 items-center justify-start pl-2 pr-3">
						<AssigneeFilter v-model="assigneeFilter" :users="assigneeOptions" />
					</div>
				</div>
				<MisList
					v-if="filteredRows.length"
					:rows="filteredRows"
					:selected-name="selectedName"
					@select="openSummary"
				/>
				<div
					v-else
					class="col-span-8 flex flex-1 flex-col items-center justify-center gap-2 px-6 py-16 text-center"
				>
					<p class="font-medium text-ink-gray-9">No Monthly Implementation Summaries found</p>
					<p class="max-w-sm text-sm text-ink-gray-6">
						Try clearing search or filters, or select Closed to include closed records.
					</p>
				</div>
			</div>
		</section>

		<!-- Host first in DOM so Teleport target exists before MisDetail mounts; order keeps it far right. -->
		<aside
			v-if="selectedName"
			id="mis-properties-host"
			class="order-3 flex w-72 flex-none flex-col overflow-hidden border-l border-outline-gray-2 bg-surface-white"
		/>

		<aside
			v-if="selectedName"
			class="order-2 flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden border-r border-outline-gray-2 bg-surface-white"
		>
			<div
				v-if="detailLoading && !selectedSummary"
				class="flex flex-1 items-center justify-center text-sm text-ink-gray-5"
			>
				Loading…
			</div>
			<MisDetail
				v-else-if="selectedSummary"
				:summary="selectedSummary"
				:options="formOptions"
				:api-prefix="API"
				@close="closeSummary"
				@updated="onSummaryUpdated"
			/>
		</aside>
	</div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { call } from "frappe-ui"
import AssigneeFilter from "../components/AssigneeFilter.vue"
import ListSortSelector from "@spa/components/ListSortSelector.vue"
import { assigneeUsersFromRow } from "../avatar.js"
import MisDetail from "../components/MisDetail.vue"
import MisList from "../components/MisList.vue"
import MisStatusFilter from "../components/MisStatusFilter.vue"
import {
	MIS_LIST_FILTER_GRID,
	MIS_LIST_FILTER_SUBGRID,
	MIS_MONTHS,
	MIS_STATUSES,
} from "../misListColumns.js"
import spaConfig from "@/config"

const API = spaConfig.api

const route = useRoute()
const router = useRouter()

const search = ref("")
const statusFilter = ref([])
const implementationFilter = ref("")
const monthFilter = ref("")
const assigneeFilter = ref([])
const sortBy = ref("modified")
const sortOrder = ref("desc")
const totalHoursSortOption = [{ label: "Total Hours", value: "total_hours" }]
const billableHoursSortOption = [{ label: "Billable Hours", value: "billable_hours" }]
const deltaSortOption = [{ label: "Delta", value: "delta_hours" }]
const monthOptions = [
	{ label: "All Months", value: "" },
	...MIS_MONTHS.map((month) => ({ label: month, value: month })),
]
const loading = ref(false)
const configError = ref("")
const rows = ref([])
const selectedName = ref(null)
const selectedSummary = ref(null)
const detailLoading = ref(false)
const formOptions = ref({
	shortlist_users: [],
})

const implementationOptions = computed(() => {
	const names = [
		...new Set(rows.value.map((r) => r.implementation).filter(Boolean)),
	].sort((a, b) => String(a).localeCompare(String(b)))
	return [{ label: "All Implementations", value: "" }, ...names.map((n) => ({ label: n, value: n }))]
})

function compareRows(a, b) {
	const field = sortBy.value
	if (field === "total_hours" || field === "billable_hours" || field === "delta_hours") {
		const cmp = Number(a[field] || 0) - Number(b[field] || 0)
		return sortOrder.value === "desc" ? -cmp : cmp
	}
	const cmp = String(a.modified || "").localeCompare(String(b.modified || ""))
	return sortOrder.value === "desc" ? -cmp : cmp
}

function rowMatchesSearch(row, q) {
	const fields = [
		row.name,
		row.implementation,
		row.month,
		row.year,
		...(row.assignee_names || []),
	]
	return fields.filter(Boolean).some((v) => String(v).toLowerCase().includes(q))
}

/** Rows after search / implementation / month / status — used for assignee options. */
const contextRows = computed(() => {
	const q = search.value.trim().toLowerCase()
	const statuses = statusFilter.value
	const implementation = implementationFilter.value
	const month = monthFilter.value
	let list = rows.value
	if (statuses.length) {
		const allowed = new Set(statuses)
		list = list.filter((r) => allowed.has(r.status))
	} else {
		list = list.filter((r) => r.status !== "Closed")
	}
	if (implementation) {
		list = list.filter((r) => r.implementation === implementation)
	}
	if (month) {
		list = list.filter((r) => r.month === month)
	}
	if (q) {
		list = list.filter((r) => rowMatchesSearch(r, q))
	}
	return list
})

const assigneeOptions = computed(() => {
	const byName = new Map()
	for (const row of contextRows.value) {
		for (const user of assigneeUsersFromRow(row)) {
			if (!user.name || byName.has(user.name)) continue
			byName.set(user.name, user)
		}
	}
	return [...byName.values()].sort((a, b) =>
		String(a.full_name || a.name).localeCompare(String(b.full_name || b.name))
	)
})

const filteredRows = computed(() => {
	const assignees = assigneeFilter.value
	let list = contextRows.value
	if (assignees.length) {
		const allowed = new Set(assignees)
		list = list.filter((r) => (r.assignees || []).some((id) => allowed.has(id)))
	}
	return [...list].sort(compareRows)
})

watch(assigneeOptions, (users) => {
	const available = new Set(users.map((u) => u.name))
	const next = (assigneeFilter.value || []).filter((id) => available.has(id))
	if (next.length !== assigneeFilter.value.length) {
		assigneeFilter.value = next
	}
})

async function loadOptions() {
	try {
		formOptions.value = await call(`${API}.get_form_options`)
	} catch {
		formOptions.value = { shortlist_users: [] }
	}
}

async function loadRows() {
	loading.value = true
	try {
		rows.value = await call(`${API}.get_monthly_implementation_summaries`)
		configError.value = ""
	} catch (e) {
		configError.value =
			e?.messages?.[0] || e?.message || "Could not load Monthly Implementation Summaries"
	} finally {
		loading.value = false
	}
}

async function openSummary(name) {
	selectedName.value = name
	if (route.params.name !== name) {
		router.replace({ name: "MisDetail", params: { name } })
	}
	detailLoading.value = true
	try {
		selectedSummary.value = await call(`${API}.get_monthly_implementation_summary`, { name })
	} catch (e) {
		configError.value =
			e?.messages?.[0] || e?.message || "Could not load Monthly Implementation Summary"
		selectedName.value = null
		selectedSummary.value = null
		router.replace({ name: "MisList" })
	} finally {
		detailLoading.value = false
	}
}

function closeSummary() {
	selectedName.value = null
	selectedSummary.value = null
	router.replace({ name: "MisList" })
}

async function onSummaryUpdated(summary) {
	if (summary?.name) {
		selectedSummary.value = summary
	}
	await loadRows()
}

watch(
	() => route.params.name,
	(name) => {
		if (name && name !== selectedName.value) openSummary(name)
		if (!name) {
			selectedName.value = null
			selectedSummary.value = null
		}
	}
)

onMounted(async () => {
	await Promise.all([loadOptions(), loadRows()])
	if (route.params.name) {
		await openSummary(route.params.name)
	}
})
</script>
