<template>
	<div class="flex h-full min-h-0 flex-col bg-surface-white">
		<div v-if="configError" class="flex flex-1 items-center justify-center px-6 text-center text-sm text-red-600">
			{{ configError }}
		</div>
		<div v-else-if="loading" class="flex flex-1 items-center justify-center text-sm text-ink-gray-5">
			Loading…
		</div>
		<template v-else>
			<div class="flex flex-shrink-0 items-center justify-between border-b border-outline-gray-2 px-5 py-3">
				<p class="text-sm text-ink-gray-6">
					{{ filteredDemos.length }} demo{{ filteredDemos.length === 1 ? "" : "s" }}
				</p>
			</div>
			<div :class="[DEMO_LIST_FILTER_GRID, 'min-h-0 flex-1 content-start overflow-y-auto px-5']">
				<div
					:class="[
						DEMO_LIST_FILTER_SUBGRID,
						'sticky top-0 z-[1] border-b border-outline-gray-2 bg-surface-white py-3',
					]"
				>
					<FormControl v-model="search" type="text" size="sm" placeholder="Search…" class="w-full min-w-0" />
					<div class="flex min-w-0 justify-center">
						<StatusFilter v-model="statusFilter" :statuses="statuses" />
					</div>
					<div class="flex min-w-0 justify-center">
						<ListSortSelector
							standalone
							v-model:sort-by="sortBy"
							v-model:sort-order="sortOrder"
							:options="scheduledSortOption"
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
				</div>

				<div
					v-if="truncated"
					style="grid-column: 1 / -1"
					class="border-b border-outline-gray-2 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:bg-amber-950 dark:text-amber-200"
				>
					Showing the latest {{ demos.length }} demos — narrow your filters to see older ones.
				</div>

				<a
					v-for="demo in filteredDemos"
					:key="demo.name"
					:href="`/app/demo/${demo.name}`"
					:class="[DEMO_LIST_FILTER_SUBGRID, 'border-b border-outline-gray-1 py-3 hover:bg-surface-gray-2']"
				>
					<div class="min-w-0">
						<div class="truncate text-sm font-medium text-ink-gray-9">{{ demo.subject }}</div>
						<div class="truncate text-xs text-ink-gray-6">
							{{ demo.lead_name || demo.lead }}
						</div>
						<div v-if="demo.owner_name" class="mt-0.5 truncate text-xs text-ink-gray-5">
							{{ demo.owner_name }}
						</div>
					</div>
					<div class="flex min-w-0 items-center justify-center">
						<Badge :label="demo.status" :theme="statusTheme(demo.status)" size="sm" variant="subtle" />
					</div>
					<div class="min-w-0 text-center text-xs text-ink-gray-6">
						{{ demo.scheduled_on ? formatDatetime(demo.scheduled_on) : "Not scheduled" }}
					</div>
					<div class="min-w-0 text-center text-xs text-ink-gray-6">
						{{ demo.modified ? formatDate(demo.modified) : "—" }}
					</div>
				</a>

				<div
					v-if="!filteredDemos.length"
					style="grid-column: 1 / -1"
					class="flex flex-1 flex-col items-center justify-center gap-1 px-6 py-16 text-center text-sm text-ink-gray-6"
				>
					No demos found. Create one from a lead in Follow Ups.
				</div>
			</div>
		</template>
	</div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue"
import { call, Badge } from "frappe-ui"
import StatusFilter from "@spa/components/StatusFilter.vue"
import ListSortSelector from "@spa/components/ListSortSelector.vue"
import { formatDate, formatDatetime } from "@spa/utils/datetime"
import { DEMO_LIST_FILTER_GRID, DEMO_LIST_FILTER_SUBGRID, demoStatusTheme } from "@/demoListColumns.js"

const API = "phamos.api.sales_demos"

const scheduledSortOption = [{ label: "Scheduled", value: "scheduled_on" }]
const modifiedSortOption = [{ label: "Last Updated", value: "modified" }]

const search = ref("")
const statusFilter = ref([])
const sortBy = ref("scheduled_on")
const sortOrder = ref("asc")
const loading = ref(false)
const configError = ref("")
const demos = ref([])
const statuses = ref([])
const truncated = ref(false)

const statusTheme = demoStatusTheme

function matchesSearch(demo, q) {
	return [demo.name, demo.subject, demo.lead, demo.lead_name, demo.owner_name]
		.filter(Boolean)
		.some((v) => String(v).toLowerCase().includes(q))
}

function compareDemos(a, b) {
	const field = sortBy.value === "modified" ? "modified" : "scheduled_on"
	const av = a[field]
	const bv = b[field]
	// Unscheduled demos sit at the top of the scheduled view — they still need a date.
	if (field === "scheduled_on") {
		if (!av && !bv) return 0
		if (!av) return -1
		if (!bv) return 1
	}
	const cmp = String(av || "").localeCompare(String(bv || ""))
	return sortOrder.value === "desc" ? -cmp : cmp
}

const filteredDemos = computed(() => {
	const q = search.value.trim().toLowerCase()
	let list = demos.value
	if (statusFilter.value.length) {
		const allowed = new Set(statusFilter.value)
		list = list.filter((d) => allowed.has(d.status))
	}
	if (q) list = list.filter((d) => matchesSearch(d, q))
	return [...list].sort(compareDemos)
})

async function loadDemos() {
	loading.value = true
	try {
		const data = await call(`${API}.get_demos`)
		demos.value = data.items || []
		statuses.value = data.statuses || []
		truncated.value = Boolean(data.truncated)
		configError.value = ""
	} catch (e) {
		configError.value = e?.messages?.[0] || e?.message || "Could not load demos"
	} finally {
		loading.value = false
	}
}

onMounted(loadDemos)
</script>
