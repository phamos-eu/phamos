<template>
	<!-- Timesheets (#1685): what /timesheet shows, for the open implementation only. -->
	<div class="h-full min-h-0 overflow-y-auto bg-surface-gray-1 p-5">
		<div class="mx-auto flex max-w-7xl flex-col gap-5">
			<div class="flex flex-wrap items-end gap-3">
				<FormControl v-model="sheets.filters.from" type="date" size="sm" :label="__('From')" class="w-40" @change="applyFilters" />
				<FormControl v-model="sheets.filters.to" type="date" size="sm" :label="__('To')" class="w-40" @change="applyFilters" />
				<FormControl
					v-model="sheets.filters.project"
					type="select"
					size="sm"
					:label="__('Project')"
					class="w-56"
					:options="projectOptions"
					@change="applyFilters"
				/>
				<Button variant="ghost" @click="resetFilters">{{ __("Reset filters") }}</Button>
				<div class="ml-auto flex items-center gap-2">
					<TabButtons v-model="group" :buttons="groupButtons" />
					<Button variant="subtle" :loading="exporting" @click="downloadCsv">
						<template #prefix><FeatherIcon name="download" class="h-4 w-4" /></template>
						{{ selected.size ? __("Download selected ({0})", [selected.size]) : __("Download CSV") }}
					</Button>
				</div>
			</div>

			<div v-if="sheets.error" class="rounded-lg border border-outline-gray-2 bg-surface-red-1 p-4 text-sm text-ink-red-4">
				{{ sheets.error }}
			</div>

			<section class="grid grid-cols-2 gap-3 xl:grid-cols-4">
				<StatCard :label="__('Hours')" :value="formatHours(summary?.hours)" />
				<StatCard :label="__('Billable')" :value="formatHours(summary?.billable_hours)" />
				<StatCard :label="__('Non-billable')" :value="formatHours(summary?.non_billable_hours)" />
				<StatCard :label="__('Timesheets')" :value="summary ? summary.count : '—'" />
			</section>

			<PeriodBars
				:title="__('Hours per {0}', [group === 'week' ? __('week') : __('month')])"
				:subtitle="sheets.filters.project ? projectLabel(sheets.filters.project) : __('All projects')"
				:periods="periods"
				:series="[{ label: __('Hours') }, { label: __('Billable') }]"
				:format="(value) => formatHours(value)"
			/>

			<section class="overflow-hidden rounded-lg border border-outline-gray-2 bg-surface-white">
				<div class="overflow-x-auto">
					<div class="min-w-[960px]">
						<div :class="[GRID, 'border-b border-outline-gray-2 bg-surface-gray-1 py-2 text-xs font-medium text-ink-gray-5']">
							<input
								type="checkbox"
								class="rounded border-outline-gray-3"
								:checked="allSelected"
								:aria-label="__('Select all')"
								@change="toggleAll($event.target.checked)"
							/>
							<button
								v-for="col in COLUMNS"
								:key="col.key"
								type="button"
								class="flex min-w-0 items-center gap-1 text-left hover:text-ink-gray-8"
								:class="col.align === 'right' ? 'justify-end' : ''"
								:disabled="!col.sort"
								@click="col.sort && sortBy(col.sort)"
							>
								<span class="truncate">{{ __(col.label) }}</span>
								<FeatherIcon
									v-if="col.sort && sheets.sort.by === col.sort"
									:name="sheets.sort.order === 'asc' ? 'arrow-up' : 'arrow-down'"
									class="h-3 w-3 flex-shrink-0"
								/>
							</button>
						</div>

						<div
							v-for="row in sheets.rows"
							:key="row.name"
							:class="[GRID, 'border-b border-outline-gray-1 py-2.5 text-sm hover:bg-surface-gray-1']"
						>
							<input
								type="checkbox"
								class="rounded border-outline-gray-3"
								:checked="selected.has(row.name)"
								:aria-label="__('Select {0}', [row.name])"
								@change="toggle(row.name, $event.target.checked)"
							/>
							<span class="truncate text-xs font-semibold text-ink-gray-6">{{ row.name }}</span>
							<span class="tabular-nums text-ink-gray-7">{{ formatDate(row.start_date) }}</span>
							<span class="truncate text-ink-gray-8">{{ row.employee_name }}</span>
							<span class="truncate text-ink-gray-7">{{ row.activity_type || "—" }}</span>
							<span>
								<span v-if="row.custom_billing_status" class="inline-flex h-5 items-center rounded-full px-1.5 text-xs font-semibold" :class="billingClass(row.custom_billing_status)">
									{{ __(row.custom_billing_status) }}
								</span>
							</span>
							<span class="text-right tabular-nums text-ink-gray-8">{{ formatHours(row.total_hours) }}</span>
							<span class="text-right tabular-nums text-ink-gray-8">{{ formatHours(row.total_billable_hours) }}</span>
							<span class="truncate text-ink-gray-7" :title="row.related_issue || ''">{{ row.related_issue || "—" }}</span>
							<span class="text-right">
								<Button size="sm" :variant="row.custom_rating > 0 ? 'subtle' : 'outline'" @click="openFeedback(row)">
									{{ row.custom_rating > 0 ? __("Under review") : __("Give feedback") }}
								</Button>
							</span>
						</div>

						<div v-if="!sheets.loading && !sheets.rows.length" class="px-4 py-8 text-center text-sm text-ink-gray-5">
							{{ __("No timesheets for these filters.") }}
						</div>
					</div>
				</div>

				<div class="flex flex-wrap items-center gap-3 border-t border-outline-gray-2 px-4 py-2.5 text-xs text-ink-gray-6">
					<span>{{ __("Showing {0} of {1}", [sheets.rows.length, sheets.total]) }}</span>
					<div class="flex items-center gap-1">
						<span>{{ __("Rows") }}</span>
						<TabButtons v-model="pageLength" :buttons="PAGE_SIZES.map((n) => ({ label: String(n), value: n }))" />
					</div>
					<Button v-if="sheets.rows.length < sheets.total" class="ml-auto" size="sm" :loading="loadingMore" @click="more">
						{{ __("Load more") }}
					</Button>
				</div>
			</section>
		</div>

		<FeedbackDialog v-model="showFeedback" :timesheet="feedbackRow" @saved="reloadTimesheets" />
	</div>
</template>

<script setup>
import { computed, reactive, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import dayjs from "dayjs"
import { TabButtons } from "frappe-ui"
import PeriodBars from "@spa/components/dashboard/PeriodBars.vue"
import StatCard from "@spa/components/dashboard/StatCard.vue"
import { __ } from "@spa/utils/i18n.js"
import FeedbackDialog from "../components/FeedbackDialog.vue"
import {
	PAGE_SIZES,
	exportTimesheets,
	initTimesheets,
	loadMoreTimesheets,
	reloadTimesheets,
	sheets,
} from "../timesheetStore.js"

const props = defineProps({ implementation: { type: String, required: true } })

const route = useRoute()
const router = useRouter()

const GRID =
	"grid grid-cols-[1.25rem_7rem_6rem_minmax(0,1fr)_minmax(0,0.8fr)_6.5rem_4.5rem_4.5rem_minmax(0,1.6fr)_8rem] items-center gap-x-4 px-4"
const COLUMNS = [
	{ key: "name", label: "Timesheet", sort: "name" },
	{ key: "start", label: "Start", sort: "start_date" },
	{ key: "employee", label: "Employee", sort: "employee_name" },
	{ key: "activity", label: "Activity" },
	{ key: "billing", label: "Billing status", sort: "billing_status" },
	{ key: "hours", label: "Hours", sort: "total_hours", align: "right" },
	{ key: "billable", label: "Billable", sort: "billable_hours", align: "right" },
	{ key: "issue", label: "Related issue" },
	{ key: "feedback", label: "Feedback", sort: "rating", align: "right" },
]

const selected = reactive(new Set())
const loadingMore = ref(false)
const exporting = ref(false)
const showFeedback = ref(false)
const feedbackRow = ref(null)

const summary = computed(() => sheets.summary)
const projectOptions = computed(() => [
	{ label: __("All projects"), value: "" },
	...sheets.projects.map((p) => ({ label: p.project_name || p.name, value: p.name })),
])
const groupButtons = computed(() => [
	{ label: __("Weeks"), value: "week" },
	{ label: __("Months"), value: "month" },
])
const group = computed({
	get: () => sheets.filters.group,
	set: (value) => {
		sheets.filters.group = value
		applyFilters()
	},
})
const pageLength = computed({
	get: () => sheets.pageLength,
	set: (value) => {
		sheets.pageLength = value
		reloadTimesheets()
	},
})
const periods = computed(() =>
	(summary.value?.periods || []).map((p) => ({
		key: String(p.start),
		label: sheets.filters.group === "week" ? dayjs(p.start).format("D MMM") : dayjs(p.start).format("MMM YY"),
		values: [p.hours, p.billable],
	}))
)
const allSelected = computed(() => sheets.rows.length > 0 && sheets.rows.every((r) => selected.has(r.name)))

watch(
	() => props.implementation,
	(implementation) => {
		selected.clear()
		initTimesheets(implementation, route.query)
	},
	{ immediate: true }
)

function applyFilters() {
	selected.clear()
	const { from, to, project, group: g } = sheets.filters
	router.replace({ query: { from: from || undefined, to: to || undefined, project: project || undefined, group: g } })
	reloadTimesheets()
}

function resetFilters() {
	sheets.filters = { ...sheets.filters, from: sheets.defaults.from, to: sheets.defaults.to, project: "" }
	applyFilters()
}

function sortBy(field) {
	sheets.sort =
		sheets.sort.by === field
			? { by: field, order: sheets.sort.order === "asc" ? "desc" : "asc" }
			: { by: field, order: field === "start_date" ? "desc" : "asc" }
	reloadTimesheets()
}

async function more() {
	loadingMore.value = true
	try {
		await loadMoreTimesheets()
	} finally {
		loadingMore.value = false
	}
}

function toggle(name, on) {
	if (on) selected.add(name)
	else selected.delete(name)
}

function toggleAll(on) {
	for (const row of sheets.rows) toggle(row.name, on)
}

function openFeedback(row) {
	feedbackRow.value = row
	showFeedback.value = true
}

function projectLabel(name) {
	const project = sheets.projects.find((p) => p.name === name)
	return project?.project_name || name
}

function formatHours(value) {
	if (value == null) return "—"
	const minutes = Math.round(Number(value) * 60)
	const h = Math.floor(minutes / 60)
	const m = minutes % 60
	return m ? `${h} h ${m} min` : `${h} h`
}

function formatDate(value) {
	return value ? dayjs(value).format("D MMM YYYY") : ""
}

function billingClass(status) {
	if (status === "Billed") return "bg-surface-green-2 text-ink-green-3"
	if (status === "In Question") return "bg-surface-amber-2 text-ink-amber-3"
	return "bg-surface-gray-2 text-ink-gray-6"
}

async function downloadCsv() {
	exporting.value = true
	try {
		const rows = selected.size ? sheets.rows.filter((r) => selected.has(r.name)) : await exportTimesheets()
		const header = ["Timesheet", "Start", "Employee", "Activity", "Billing status", "Hours", "Billable hours", "Project", "Related issue", "Rating", "Comment"]
		const lines = [header, ...rows.map((r) => [
			r.name,
			r.start_date,
			r.employee_name,
			r.activity_type,
			r.custom_billing_status,
			r.total_hours,
			r.total_billable_hours,
			r.project_name || r.parent_project,
			r.related_issue,
			r.custom_rating || "",
			r.customer_comment,
		])]
		const csv = lines.map((line) => line.map(csvCell).join(",")).join("\r\n")
		const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" })
		const link = document.createElement("a")
		link.href = URL.createObjectURL(blob)
		link.download = `timesheets-${props.implementation}-${sheets.filters.from || "all"}-${sheets.filters.to || "all"}.csv`
		link.click()
		URL.revokeObjectURL(link.href)
	} finally {
		exporting.value = false
	}
}

function csvCell(value) {
	let text = value == null ? "" : String(value)
	// Spreadsheets run cells starting with these as formulas.
	if (/^[=+\-@\t\r]/.test(text)) text = `'${text}`
	return `"${text.replace(/"/g, '""')}"`
}
</script>
