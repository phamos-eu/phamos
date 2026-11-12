<template>
	<!-- Lead overview for reporting to management (#1758). Every figure opens the leads behind it. -->
	<div class="h-full overflow-y-auto bg-surface-gray-1">
		<div class="space-y-5 p-5">
			<div class="flex flex-wrap items-center gap-3">
				<div class="inline-flex rounded-md bg-surface-gray-2 p-0.5" role="group" :aria-label="__('Inbound / Outbound')">
					<button
						v-for="option in directionOptions"
						:key="option.value"
						type="button"
						class="rounded px-3 py-1 text-sm"
						:class="direction === option.value ? 'bg-surface-white font-medium text-ink-gray-9 shadow-sm' : 'text-ink-gray-6 hover:text-ink-gray-9'"
						:aria-pressed="direction === option.value"
						@click="setDirection(option.value)"
					>
						{{ option.label }}
					</button>
				</div>
				<p v-if="data" class="text-sm text-ink-gray-5">
					{{ __("As of {0}. Counted by the date a lead was created.", [formatDate(data.today)]) }}
				</p>
				<a :href="deskAllUrl" class="ml-auto inline-flex items-center gap-1 text-sm text-ink-gray-6 hover:text-ink-gray-9">
					{{ __("Lead list in Desk") }}<FeatherIcon name="external-link" class="h-3.5 w-3.5" />
				</a>
			</div>

			<div v-if="error" class="rounded-lg border border-outline-gray-2 bg-surface-white p-6 text-sm text-ink-red-3">{{ error }}</div>
			<div v-else-if="!data" class="p-6 text-sm text-ink-gray-5">{{ __("Loading…") }}</div>
			<template v-else>
				<!-- Not set first: it makes every split below incomplete. -->
				<button
					v-if="data.not_set && data.not_set.count"
					type="button"
					class="flex w-full items-center gap-3 rounded-lg border border-outline-amber-2 bg-surface-amber-1 px-4 py-3 text-left text-sm text-ink-amber-4 hover:bg-surface-amber-2"
					@click="openList(data.not_set.filters)"
				>
					<FeatherIcon name="alert-triangle" class="h-4 w-4 flex-shrink-0" />
					<span class="flex-1">
						{{
							data.not_set.count === 1
								? __("1 lead is not marked Inbound or Outbound yet, so the split below is incomplete.")
								: __("{0} leads are not marked Inbound or Outbound yet, so the split below is incomplete.", [data.not_set.count])
						}}
					</span>
					<span class="font-medium">{{ __("Show them") }} →</span>
				</button>

				<div class="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
					<button v-for="card in kpiCards" :key="card.key" type="button" class="text-left" @click="card.open()">
						<StatCard :label="card.label" :value="card.value" :hint="card.hint" class="h-full transition-colors hover:border-outline-gray-4">
							<div v-if="card.comparison" class="mt-2 text-sm font-medium" :class="toneClass(card.tone)">{{ card.comparison }}</div>
							<div v-if="card.split" class="mt-2 text-xs text-ink-gray-5">{{ card.split }}</div>
						</StatCard>
					</button>
				</div>

				<div class="grid grid-cols-1 gap-4 md:grid-cols-3">
					<button v-for="trend in trendCards" :key="trend.key" type="button" class="text-left" @click="trend.open()">
						<StatCard :label="trend.label" :value="trend.value" :hint="trend.hint" class="h-full transition-colors hover:border-outline-gray-4">
							<div class="mt-2 text-sm font-medium" :class="toneClass(trend.tone)">{{ trend.comparison }}</div>
						</StatCard>
					</button>
				</div>

				<PeriodBars
					:title="__('New leads per month')"
					:subtitle="__('Click a month to see its leads. The current month runs up to today.')"
					:periods="chartPeriods"
					:series="chartSeries"
					:colors="['var(--ink-blue-3)', 'var(--ink-gray-4)']"
					:format="(value) => String(value)"
					selectable
					@select="(period) => openList(period.filters)"
				/>

				<div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
					<div>
						<div class="mb-2 flex justify-end">
							<div class="inline-flex rounded-md bg-surface-gray-2 p-0.5 text-xs">
								<button
									v-for="option in sourceRanges"
									:key="option.value"
									type="button"
									class="rounded px-2 py-0.5"
									:class="sourceRange === option.value ? 'bg-surface-white font-medium text-ink-gray-9 shadow-sm' : 'text-ink-gray-6'"
									@click="sourceRange = option.value"
								>
									{{ option.label }}
								</button>
							</div>
						</div>
						<HorizontalBars
							:title="__('Where leads come from')"
							:rows="sourceRows"
							:empty-text="__('No leads in this period.')"
							selectable
							@select="(row) => openList(row.filters)"
						/>
					</div>
					<div class="lg:pt-8">
						<HorizontalBars
							:title="__('This month\'s leads by status today')"
							:rows="statusRows"
							:empty-text="__('No leads this month yet.')"
							selectable
							@select="(row) => openList(row.filters)"
						/>
					</div>
				</div>
			</template>
		</div>

		<LeadOverviewDialog
			v-model="dialog.open"
			:title="dialog.title"
			:intro="dialog.intro"
			:note="dialog.note"
			:empty-text="dialog.emptyText"
			:sections="dialog.sections"
			@open-list="openList"
		/>
	</div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { call, FeatherIcon } from "frappe-ui"
import StatCard from "@spa/components/dashboard/StatCard.vue"
import PeriodBars from "@spa/components/dashboard/PeriodBars.vue"
import HorizontalBars from "@spa/components/dashboard/HorizontalBars.vue"
import { formatDate, userLocale } from "@spa/utils/datetime"
import { __ } from "@spa/utils/i18n.js"
import { createdRangeLabel, leadDeskListUrl, monthLabel, NOT_SET, OVERVIEW_BACK_KEY } from "@spa/utils/leadFilters.js"
import { leadStatusLabel, leadStatusTheme } from "@/leadListColumns.js"
import LeadOverviewDialog from "@/components/LeadOverviewDialog.vue"

const API = "phamos.api.sales_lead_overview"

const route = useRoute()
const router = useRouter()
const data = ref(null)
const error = ref("")
const sourceRange = ref("this_month")
const dialog = reactive({ open: false, title: "", intro: "", note: "", emptyText: undefined, sections: [] })

const directionOptions = [
	{ value: "", label: __("All leads") },
	{ value: "Inbound", label: __("Inbound") },
	{ value: "Outbound", label: __("Outbound") },
]
const sourceRanges = [
	{ value: "this_month", label: __("This month") },
	{ value: "last_3_months", label: __("Last 3 months") },
]

const direction = computed(() => (["Inbound", "Outbound"].includes(route.query.direction) ? route.query.direction : ""))
const deskAllUrl = computed(() => leadDeskListUrl(direction.value ? { direction: direction.value } : {}))

let request = 0

async function load() {
	const mine = ++request
	error.value = ""
	data.value = null
	try {
		const result = await call(`${API}.get_lead_overview`, { direction: direction.value || null })
		if (mine === request) data.value = result
	} catch (e) {
		if (mine === request) error.value = e?.messages?.[0] || e?.message || __("Could not load the lead overview")
	}
}

function setDirection(value) {
	router.replace({ name: "LeadsOverview", query: value ? { direction: value } : {} })
}

/** The leads behind a figure, remembering which overview view to go back to. */
function openList(filters) {
	router.push({ name: "LeadsFollowUps", query: { ...filters, [OVERVIEW_BACK_KEY]: direction.value || "all" } })
}

// --- wording -------------------------------------------------------------------------------------------------

function toneClass(tone) {
	if (tone === "above") return "text-ink-green-3"
	if (tone === "below") return "text-ink-red-3"
	return "text-ink-gray-6"
}

function leads(count) {
	return Number(count) === 1 ? __("1 lead") : __("{0} leads", [formatNumber(count)])
}

/** 1.5 → "1,5" for a German user; whole numbers stay whole. */
function formatNumber(value) {
	return Number(value).toLocaleString(userLocale(), { maximumFractionDigits: 1 })
}

/** "2 leads more (+40%) · above", led by the absolute difference: at these volumes percent alone misleads. */
function comparisonText(c) {
	if (!c || c.delta == null) return ""
	const amount = Math.abs(Number(c.delta))
	const percent = c.percent == null ? "" : ` (${c.percent > 0 ? "+" : ""}${c.percent}%)`
	if (c.tone === "par") return __("On par") + (amount ? ` (${c.delta > 0 ? "+" : "−"}${formatNumber(amount)})` : "")
	return c.delta > 0
		? __("{0} more", [leads(amount)]) + percent
		: __("{0} fewer", [leads(amount)]) + percent
}

function splitText(split) {
	if (!split) return ""
	const parts = [`${__("Inbound")} ${split.Inbound}`, `${__("Outbound")} ${split.Outbound}`]
	if (split[NOT_SET]) parts.push(`${__("Not set")} ${split[NOT_SET]}`)
	return parts.join(" · ")
}

function rangeText(item) {
	return createdRangeLabel(item.from, item.to)
}

// --- cards ---------------------------------------------------------------------------------------------------

const kpiCards = computed(() => {
	const d = data.value
	if (!d) return []
	const ly = d.last_year
	const avg = d.average
	const season = d.season
	return [
		{
			key: "this_month",
			label: __("New leads this month"),
			value: d.this_month.count,
			hint: rangeText(d.this_month),
			split: direction.value ? "" : splitText(d.this_month.split),
			open: () => openList(d.this_month.filters),
		},
		{
			key: "last_year",
			label: __("Same period last year"),
			value: ly.has_data ? ly.count : "—",
			hint: ly.has_data ? rangeText(ly) : __("No leads recorded that far back."),
			comparison: ly.has_data ? __("This month: {0}", [comparisonText(ly)]) : "",
			tone: ly.tone,
			split: ly.has_data && !direction.value ? splitText(ly.split) : "",
			open: () => openList(ly.filters),
		},
		{
			key: "average",
			label: __("Compared with the 12-month average"),
			value: avg ? formatNumber(avg.expected) : "—",
			hint: avg
				? __("Expected by today: Ø {0} a month over {1} months, for {2} of {3} days", [
						formatNumber(avg.monthly),
						avg.months_used,
						d.days_elapsed,
						d.days_in_month,
					])
				: __("Needs at least one complete month."),
			comparison: avg ? __("This month: {0}", [comparisonText(avg)]) : "",
			tone: avg?.tone,
			open: openAverageDialog,
		},
		{
			key: "season",
			label: __("Compared with this month in earlier years"),
			value: season ? formatNumber(season.expected) : "—",
			hint: season
				? __("Ø of the same days in {0}", [season.years.map((y) => y.year).join(", ")])
				: __("Not enough history yet: the first lead is from {0}.", [monthLabel(d.first_lead) || "—"]),
			comparison: season ? __("This month: {0}", [comparisonText(season)]) : "",
			tone: season?.tone,
			open: openSeasonDialog,
		},
	]
})

const trendCards = computed(() => {
	const d = data.value
	if (!d) return []
	return d.trends.map((t) => ({
		key: t.months,
		label: t.months === 1 ? __("Last month vs the month before") : __("Last {0} months vs the {0} before", [t.months]),
		value: t.has_data ? `${t.delta > 0 ? "+" : ""}${t.delta}` : "—",
		hint: t.has_data
			? __("{0} against {1} · {2}", [leads(t.current.count), leads(t.previous.count), rangeText(t.current)])
			: __("Not enough history yet."),
		comparison: t.has_data ? trendWord(t) : "",
		tone: t.tone,
		open: () => openTrendDialog(t),
	}))
})

function trendWord(t) {
	if (t.tone === "par") return __("Steady") + (t.percent != null ? ` (${t.percent > 0 ? "+" : ""}${t.percent}%)` : "")
	const percent = t.percent != null ? ` (${t.percent > 0 ? "+" : ""}${t.percent}%)` : ""
	return (t.tone === "above" ? __("Improved") : __("Declined")) + percent
}

const chartSeries = computed(() => [{ label: __("Leads") }, { label: __("Same month a year earlier") }])

const chartPeriods = computed(() =>
	(data.value?.chart || []).map((m) => ({
		key: m.key,
		label: monthLabel(m.key),
		values: [m.count, m.last_year ?? 0],
		footer: m.count,
		footerTone: m.last_year == null || m.count === m.last_year ? null : m.count > m.last_year ? "good" : "bad",
		filters: m.filters,
	}))
)

const sourceRows = computed(() =>
	(data.value?.by_source?.[sourceRange.value] || []).map((row) => ({
		key: row.key,
		label: row.key === NOT_SET ? __("No source") : row.label,
		value: row.count,
		theme: row.key === NOT_SET ? "amber" : "blue",
		filters: row.filters,
	}))
)

const statusRows = computed(() =>
	(data.value?.by_status || []).map((row) => ({
		key: row.key,
		label: leadStatusLabel(row.label),
		value: row.count,
		theme: { red: "red", green: "green", orange: "amber" }[leadStatusTheme(row.label)] || "blue",
		filters: row.filters,
	}))
)

// --- dialogs -------------------------------------------------------------------------------------------------

function showDialog(options) {
	Object.assign(dialog, { intro: "", note: "", emptyText: undefined, sections: [] }, options, { open: true })
}

function directionColumns() {
	return direction.value
		? []
		: [
				{ key: "inbound", label: __("Inbound"), numeric: true },
				{ key: "outbound", label: __("Outbound"), numeric: true },
			]
}

function directionCells(split) {
	return direction.value ? {} : { inbound: split.Inbound, outbound: split.Outbound }
}

function openAverageDialog() {
	const avg = data.value.average
	if (!avg) {
		showDialog({ title: __("12-month average"), emptyText: __("There is no complete month of leads yet.") })
		return
	}
	showDialog({
		title: __("The last {0} months", [avg.months_used]),
		intro: __("Ø {0} leads a month. Green months were above it, red ones below. Click a month to see its leads.", [
			formatNumber(avg.monthly),
		]),
		sections: [
			{
				columns: [
					{ key: "month", label: __("Month") },
					{ key: "count", label: __("Leads"), numeric: true },
					...directionColumns(),
					{ key: "diff", label: __("vs Ø"), numeric: true },
				],
				rows: [...avg.months].reverse().map((m) => ({
					key: m.key,
					query: m.filters,
					cells: {
						month: monthLabel(m.key),
						count: m.count,
						...directionCells(m.split),
						diff: `${m.delta > 0 ? "+" : ""}${formatNumber(m.delta)}`,
					},
					tones: { diff: m.tone },
				})),
			},
		],
		note: __("This month so far: {0}, where Ø {1} would be expected by today.", [
			leads(data.value.this_month.count),
			formatNumber(avg.expected),
		]),
	})
}

function openSeasonDialog() {
	const d = data.value
	if (!d.season) {
		showDialog({
			title: __("This month in earlier years"),
			emptyText: __("Not enough history yet: the first lead is from {0}. This comparison appears once a full year is recorded.", [
				monthLabel(d.first_lead) || "—",
			]),
		})
		return
	}
	showDialog({
		title: __("{0} in earlier years", [monthLabel(d.this_month.from).split(" ")[0]]),
		intro: __("The same days as this month so far, and the whole month for context. Click a number to see those leads."),
		sections: [
			{
				columns: [
					{ key: "year", label: __("Year") },
					{ key: "count", label: __("Up to day {0}", [d.days_elapsed]), numeric: true, links: true },
					{ key: "full", label: __("Whole month"), numeric: true, links: true },
				],
				rows: [
					{
						key: "now",
						query: d.this_month.filters,
						cells: { year: `${d.this_month.from.slice(0, 4)} (${__("now")})`, count: d.this_month.count, full: "—" },
						links: { count: d.this_month.filters },
					},
					...d.season.years.map((y) => ({
						key: y.year,
						cells: { year: y.year, count: y.count, full: y.full_count },
						links: { count: y.filters, full: y.full_filters },
					})),
				],
			},
		],
	})
}

function openTrendDialog(t) {
	if (!t.has_data) {
		showDialog({ title: __("What changed"), emptyText: __("Not enough history yet to compare these months.") })
		return
	}
	const columns = [
		{ key: "label", label: "" },
		{ key: "previous", label: rangeText(t.previous), numeric: true, links: true },
		{ key: "current", label: rangeText(t.current), numeric: true, links: true },
		{ key: "delta", label: __("Change"), numeric: true },
	]
	const toRows = (items, label) =>
		items.map((item) => ({
			key: item.key,
			cells: {
				label: label(item),
				previous: item.previous,
				current: item.current,
				delta: `${item.delta > 0 ? "+" : ""}${item.delta}`,
			},
			links: { previous: item.previous_filters, current: item.current_filters },
			// More leads without a direction or source is no improvement: those rows stay neutral.
			tones: { delta: item.key === NOT_SET ? "" : item.delta > 0 ? "good" : item.delta < 0 ? "bad" : "" },
		}))
	showDialog({
		title: __("What changed"),
		intro: __("{0} against {1}. Biggest drop first, so you see where leads went missing. Click a number to see those leads.", [
			leads(t.current.count),
			leads(t.previous.count),
		]),
		sections: [
			{
				title: __("Inbound / Outbound"),
				columns,
				rows: toRows(t.changes.direction, (item) => (item.key === NOT_SET ? __("Not set") : __(item.label))),
			},
			{
				title: __("Source"),
				columns,
				rows: toRows(t.changes.source, (item) => (item.key === NOT_SET ? __("No source") : item.label)),
			},
		],
	})
}

watch(direction, load)
onMounted(load)
</script>
