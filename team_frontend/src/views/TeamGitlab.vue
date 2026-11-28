<template>
	<!-- Full height, no page scroll: figures on top, chart and SLA share the rest. Team totals only. -->
	<div class="flex h-full min-h-0 flex-col gap-3 bg-surface-gray-1 p-4">
		<div v-if="error" class="rounded-lg border border-outline-gray-2 bg-surface-red-1 p-4 text-sm text-ink-red-4">
			{{ error }}
		</div>
		<div v-else-if="loading" class="flex flex-1 items-center justify-center text-sm text-ink-gray-5">
			{{ __("Loading statistics…") }}
		</div>
		<template v-else>
			<p class="text-sm text-ink-gray-6">
				{{ __("GitLab items assigned to the team's people, wherever they work; this month to {0}, compared with the same days of the previous month and of last year.", [shortDay(data.today)]) }}
			</p>

			<KpiStrip :items="kpis" grid-class="grid-cols-2 lg:grid-cols-3 2xl:grid-cols-6" />

			<div
				v-if="data.unmatched_own_items"
				class="rounded-lg border border-outline-amber-2 bg-surface-amber-1 px-3 py-2 text-sm text-ink-amber-3"
			>
				{{ __("{0} open or this month's items in the team's own implementations have an assignee that matches no employee by email; they are not counted.", [data.unmatched_own_items]) }}
			</div>

			<div class="grid min-h-0 flex-1 grid-cols-1 grid-rows-[minmax(0,1fr)_minmax(0,1fr)] gap-3 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)] xl:grid-rows-1">
				<div class="min-h-0 overflow-auto">
					<PeriodBars
						:title="__('Closed items — 12 months')"
						:subtitle="__('Own implementations, other implementations and internal repositories; opened items under each month.')"
						:periods="monthPeriods"
						:series="seriesLegend"
						compact
					/>
				</div>
				<section class="flex min-h-0 flex-col gap-3 overflow-auto rounded-lg border border-outline-gray-2 bg-surface-white p-4">
					<div>
						<h2 class="text-base font-semibold text-ink-gray-9">{{ __("Closing time this month") }}</h2>
						<table class="mt-2 w-full text-sm">
							<thead class="text-xs text-ink-gray-5">
								<tr>
									<th class="py-1 text-left font-medium" />
									<th class="py-1 text-right font-medium">{{ __("Closed") }}</th>
									<th class="py-1 text-right font-medium">{{ __("Average") }}</th>
									<th class="py-1 text-right font-medium">{{ __("Median") }}</th>
								</tr>
							</thead>
							<tbody>
								<tr v-for="row in closingRows" :key="row.label" class="border-t border-outline-gray-1">
									<td class="py-1.5 text-ink-gray-9" :title="row.hint">{{ row.label }}</td>
									<td class="py-1.5 text-right tabular-nums text-ink-gray-7">{{ row.summary.count }}</td>
									<td class="py-1.5 text-right tabular-nums text-ink-gray-7">{{ days(row.summary.average) }}</td>
									<td class="py-1.5 text-right tabular-nums text-ink-gray-7">{{ days(row.summary.median) }}</td>
								</tr>
							</tbody>
						</table>
					</div>
					<div>
						<h2 class="text-base font-semibold text-ink-gray-9">{{ __("SLA of the team's Issues") }}</h2>
						<p v-if="!data.sla" class="mt-1 text-sm text-ink-gray-5">
							{{ __("SLA tracking is switched off in Support Settings.") }}
						</p>
						<ul v-else class="mt-2 space-y-1.5 text-sm">
							<li class="flex justify-between gap-2">
								<span class="text-ink-gray-7">{{ __("Average first response") }}</span>
								<span class="tabular-nums text-ink-gray-9">{{ hoursLabel(sla.first_response_hours) }}</span>
							</li>
							<li class="flex justify-between gap-2">
								<span class="text-ink-gray-7">{{ __("First responses in time") }}</span>
								<span class="tabular-nums text-ink-gray-9">
									{{ percent(sla.responses_in_time) }}
									<span class="text-xs text-ink-gray-5">· {{ comparison(sla.responses_in_time, data.sla.previous.responses_in_time, "percent") }}</span>
								</span>
							</li>
							<li class="flex justify-between gap-2">
								<span class="text-ink-gray-7">{{ __("Resolutions in time") }}</span>
								<span class="tabular-nums text-ink-gray-9">
									{{ percent(sla.resolutions_in_time) }}
									<span class="text-xs text-ink-gray-5">· {{ comparison(sla.resolutions_in_time, data.sla.previous.resolutions_in_time, "percent") }}</span>
								</span>
							</li>
						</ul>
					</div>
				</section>
			</div>
		</template>
	</div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue"
import { call } from "frappe-ui"
import KpiStrip from "@spa/components/dashboard/KpiStrip.vue"
import PeriodBars from "@spa/components/dashboard/PeriodBars.vue"
import { formatComparison } from "@spa/utils/dashboardFormat.js"
import { __ } from "@spa/utils/i18n.js"
import spaConfig from "../config"

const loading = ref(true)
const error = ref("")
const data = ref(null)

const GROUP_COLORS = {
	own: "var(--ink-green-3)",
	other: "var(--ink-blue-3)",
	internal: "var(--ink-gray-4)",
}
const GROUP_LABELS = {
	own: __("Own implementations"),
	other: __("Other implementations"),
	internal: __("Internal"),
}
const seriesLegend = Object.keys(GROUP_COLORS).map((key) => ({ label: GROUP_LABELS[key], color: GROUP_COLORS[key] }))

function days(value) {
	return value == null ? "—" : __("{0} d", [Number(value).toLocaleString(undefined, { maximumFractionDigits: 1 })])
}

function hoursLabel(value) {
	return value == null ? "—" : `${Number(value).toLocaleString(undefined, { maximumFractionDigits: 1 })} h`
}

function percent(value) {
	return value == null ? "—" : `${Number(value).toFixed(0)} %`
}

function comparison(current, previous, kind = "number") {
	return formatComparison(current, previous, kind)
}

// The server sends ISO dates; months and days are written in the user's language.
function shortDay(value) {
	return new Date(`${value}T00:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short" })
}

function monthLabel(value) {
	return new Date(`${value}T00:00:00`).toLocaleDateString(undefined, { month: "short", year: "numeric" })
}

const current = computed(() => data.value.windows.current)
const previous = computed(() => data.value.windows.previous)
const lastYear = computed(() => data.value.windows.last_year)
const sla = computed(() => data.value.sla?.current || {})

function lines(pick, kind = "number") {
	return [
		`${comparison(pick(current.value), pick(previous.value), kind)} ${__("vs {0}", [monthLabel(previous.value.start)])}`,
		`${comparison(pick(current.value), pick(lastYear.value), kind)} ${__("vs {0}", [monthLabel(lastYear.value.start)])}`,
	].join(" · ")
}

const kpis = computed(() => {
	const c = current.value
	const open = data.value.open_items
	return [
		{ label: __("Closed"), value: c.closed_total, hint: lines((w) => w.closed_total) },
		{ label: __("Opened"), value: c.opened_total, hint: lines((w) => w.opened_total) },
		{
			label: __("Closing time, work items"),
			value: days(c.work_item_days.median),
			hint: `${__("median")} · ${lines((w) => w.work_item_days.median)}`,
		},
		{
			label: __("Closing time, parent items"),
			value: days(c.parent_item_days.median),
			hint: `${__("median")} · ${lines((w) => w.parent_item_days.median)}`,
		},
		{
			label: __("Comments per closed item"),
			value: c.comments_per_closed_item ?? "—",
			hint: lines((w) => w.comments_per_closed_item),
		},
		{
			label: __("Open items"),
			value: open.count,
			hint: open.count ? __("median age {0}, oldest {1}", [days(open.median_age_days), days(open.oldest_age_days)]) : "",
		},
	]
})

const closingRows = computed(() => [
	{
		label: __("Work items"),
		hint: __("Every item that is not a parent of others"),
		summary: current.value.work_item_days,
	},
	{
		label: __("Parent items"),
		hint: __("Items other items point to"),
		summary: current.value.parent_item_days,
	},
])

const monthPeriods = computed(() =>
	data.value.months.map((month) => ({
		label: monthLabel(month.start),
		values: [Object.keys(GROUP_COLORS).map((key) => ({ value: month.closed[key], color: GROUP_COLORS[key], label: GROUP_LABELS[key] }))],
		// One whole string per case: glued fragments read badly once translated.
		footer: month.mtd ? __("{0} opened so far", [month.opened_total]) : __("{0} opened", [month.opened_total]),
	}))
)

async function load() {
	loading.value = true
	error.value = ""
	try {
		data.value = await call(`${spaConfig.api}.get_gitlab_statistics`)
	} catch (e) {
		error.value = e.messages?.[0] || e.message || __("Could not load the statistics.")
	} finally {
		loading.value = false
	}
}

onMounted(load)
</script>
