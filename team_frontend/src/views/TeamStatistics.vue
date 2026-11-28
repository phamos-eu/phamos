<template>
	<!-- Full height, no page scroll: figures on top, the chart and the people table share the rest. -->
	<div class="flex h-full min-h-0 flex-col gap-3 bg-surface-gray-1 p-4">
		<div v-if="error" class="rounded-lg border border-outline-gray-2 bg-surface-red-1 p-4 text-sm text-ink-red-4">
			{{ error }}
		</div>
		<div v-else-if="loading" class="flex flex-1 items-center justify-center text-sm text-ink-gray-5">
			{{ __("Loading statistics…") }}
		</div>
		<template v-else>
			<div class="flex flex-wrap items-baseline justify-between gap-2">
				<p class="text-sm text-ink-gray-6">
					{{ __("{0} · this month to {1}, compared with the same days of the previous month and of last year", [data.team, shortDay(data.today)]) }}
				</p>
				<p class="text-sm tabular-nums text-ink-gray-6">
					{{ __("Year to date: {0} h logged, booked rate {1}", [hours(data.year.current.logged), percent(data.year.current.booked_rate)]) }}
					<span class="text-ink-gray-5">· {{ comparison(data.year.current.booked_rate, data.year.last_year.booked_rate, "percent") }} {{ __("vs last year") }}</span>
				</p>
			</div>

			<KpiStrip :items="kpis" grid-class="grid-cols-2 lg:grid-cols-3 2xl:grid-cols-6" />

			<div
				v-if="data.missing_hours.length"
				class="rounded-lg border border-outline-amber-2 bg-surface-amber-1 px-3 py-2 text-sm text-ink-amber-3"
			>
				{{ __("{0} without working hours (no Weekly Working Hours, no contract): left out of the rates.", [names(data.missing_hours)]) }}
			</div>

			<div class="grid min-h-0 flex-1 grid-cols-1 grid-rows-[minmax(0,1fr)_minmax(0,1fr)] gap-3 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)] xl:grid-rows-1">
				<div class="min-h-0 overflow-auto">
					<PeriodBars
						:title="__('Logged hours — 12 months')"
						:subtitle="__('Billable, non-billable customer work and internal hours; the line below each month is the booked rate.')"
						:periods="monthPeriods"
						:series="seriesLegend"
						:format="(value) => `${hours(value)} h`"
						compact
					/>
				</div>
				<section class="flex min-h-0 flex-col rounded-lg border border-outline-gray-2 bg-surface-white">
					<div class="border-b border-outline-gray-1 px-4 py-2">
						<h2 class="text-base font-semibold text-ink-gray-9">
							{{ data.sees_members ? __("Members this month") : __("Your hours this month") }}
						</h2>
						<p class="text-xs text-ink-gray-5">{{ __("Sorted by name. Rates against each person's available hours after leave and holidays.") }}</p>
					</div>
					<div class="min-h-0 flex-1 overflow-auto">
						<table class="w-full text-sm">
							<thead class="sticky top-0 bg-surface-white text-xs text-ink-gray-5">
								<tr>
									<th class="px-3 py-1.5 text-left font-medium">{{ __("Name") }}</th>
									<th class="px-3 py-1.5 text-right font-medium">{{ __("Available") }}</th>
									<th class="px-3 py-1.5 text-right font-medium">{{ __("Logged") }}</th>
									<th class="px-3 py-1.5 text-right font-medium">{{ __("Booked") }}</th>
									<th class="px-3 py-1.5 text-right font-medium">{{ __("Billable") }}</th>
									<th class="px-3 py-1.5 text-right font-medium">{{ __("Internal") }}</th>
								</tr>
							</thead>
							<tbody>
								<tr v-if="!memberRows.length">
									<td colspan="6" class="px-3 py-3 text-ink-gray-5">{{ __("No hours to show.") }}</td>
								</tr>
								<tr v-for="row in memberRows" :key="row.employee" class="border-t border-outline-gray-1">
									<td class="truncate px-3 py-1.5 text-ink-gray-9">{{ row.employee_name }}</td>
									<td class="px-3 py-1.5 text-right tabular-nums text-ink-gray-7">{{ row.known ? hours(row.available) : "—" }}</td>
									<td class="px-3 py-1.5 text-right tabular-nums text-ink-gray-9">{{ hours(row.logged) }}</td>
									<td class="px-3 py-1.5 text-right tabular-nums text-ink-gray-7">{{ percent(row.booked_rate) }}</td>
									<td class="px-3 py-1.5 text-right tabular-nums text-ink-gray-7">{{ percent(row.billable_rate) }}</td>
									<td class="px-3 py-1.5 text-right tabular-nums text-ink-gray-7">{{ hours(row.internal) }}</td>
								</tr>
							</tbody>
						</table>
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
	billable: "var(--chart-series-1)",
	non_billable: "var(--chart-series-2)",
	internal: "var(--chart-series-3)",
}
const seriesLegend = [
	{ label: __("Billable"), color: GROUP_COLORS.billable },
	{ label: __("Non-billable customer work"), color: GROUP_COLORS.non_billable },
	{ label: __("Internal"), color: GROUP_COLORS.internal },
]

function hours(value) {
	if (value == null) return "—"
	return Number(value).toLocaleString(undefined, { maximumFractionDigits: 1 })
}

function percent(value) {
	return value == null ? "—" : `${Number(value).toFixed(0)} %`
}

function comparison(current, previous, kind) {
	return formatComparison(current, previous, kind)
}

function names(rows) {
	return rows.map((r) => r.employee_name).join(", ")
}

// The server sends ISO dates; months and days are written in the user's language.
function shortDay(value) {
	return new Date(`${value}T00:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short" })
}

function monthLabel(value) {
	return new Date(`${value}T00:00:00`).toLocaleDateString(undefined, { month: "short", year: "numeric" })
}

const current = computed(() => data.value.windows.current.totals)
const previous = computed(() => data.value.windows.previous)
const lastYear = computed(() => data.value.windows.last_year)

function lines(field, kind = "number") {
	return [
		`${comparison(current.value[field], previous.value.totals[field], kind)} ${__("vs {0}", [monthLabel(previous.value.start)])}`,
		`${comparison(current.value[field], lastYear.value.totals[field], kind)} ${__("vs {0}", [monthLabel(lastYear.value.start)])}`,
	].join(" · ")
}

const kpis = computed(() => {
	const t = current.value
	const logged = t.logged || 0
	const share = (value) => (logged ? `${((value / logged) * 100).toFixed(0)} %` : "—")
	return [
		{ label: __("Booked rate"), value: percent(t.booked_rate), hint: lines("booked_rate", "percent") },
		{ label: __("Billable rate"), value: percent(t.billable_rate), hint: lines("billable_rate", "percent") },
		{ label: __("Hours per FTE"), value: hours(t.hours_per_fte), hint: lines("hours_per_fte") },
		{ label: __("Logged / available"), value: `${hours(t.logged)} / ${hours(t.available)} h`, hint: lines("logged") },
		{ label: __("Billable · non-billable"), value: `${share(t.billable)} · ${share(t.non_billable)}`, hint: __("of logged hours") },
		{ label: __("Internal"), value: share(t.internal), hint: `${hours(t.internal)} h · ${lines("internal")}` },
	]
})

const monthPeriods = computed(() =>
	data.value.months.map((month) => ({
		label: monthLabel(month.start),
		values: [
			[
				{ value: month.totals.billable, color: GROUP_COLORS.billable, label: __("Billable") },
				{ value: month.totals.non_billable, color: GROUP_COLORS.non_billable, label: __("Non-billable customer work") },
				{ value: month.totals.internal, color: GROUP_COLORS.internal, label: __("Internal") },
			],
		],
		footer: month.totals.booked_rate == null ? null : `${percent(month.totals.booked_rate)}${month.mtd ? ` ${__("so far")}` : ""}`,
	}))
)

const memberRows = computed(() => data.value.windows.current.members)

async function load() {
	loading.value = true
	error.value = ""
	try {
		data.value = await call(`${spaConfig.api}.get_hours_statistics`)
	} catch (e) {
		error.value = e.messages?.[0] || e.message || __("Could not load the statistics.")
	} finally {
		loading.value = false
	}
}

onMounted(load)
</script>
