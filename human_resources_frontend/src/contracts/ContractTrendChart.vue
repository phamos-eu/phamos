<template>
	<section class="rounded-lg border border-outline-gray-2 bg-surface-white p-5">
		<div class="mb-4 flex flex-wrap items-start justify-between gap-3">
			<div>
				<h2 class="text-base font-semibold text-ink-gray-9">Development per month</h2>
				<p class="text-sm text-ink-gray-5">
					{{ subtitle }}
					Future months add draft contracts as an estimate.
				</p>
			</div>
			<div class="flex items-center gap-2">
				<span v-if="loading" class="text-xs text-ink-gray-5">Loading…</span>
				<div class="inline-flex rounded-md bg-surface-gray-2 p-0.5" role="group" aria-label="Measure">
					<button
						v-for="option in MEASURES"
						:key="option.value"
						type="button"
						class="rounded px-3 py-1 text-sm"
						:class="measure === option.value ? 'bg-surface-white font-medium text-ink-gray-9 shadow-sm' : 'text-ink-gray-6'"
						:aria-pressed="measure === option.value"
						@click="measure = option.value"
					>
						{{ option.label }}
					</button>
				</div>
			</div>
		</div>

		<!-- Twelve months fill the card; more scroll inside it, never the page. Older and later
		     months load in pages when the user scrolls or swipes near an edge or clicks the
		     buttons on either side, which keep their place when there is nothing more. -->
		<div class="flex items-start gap-1">
			<button
				type="button"
				class="flex h-56 w-7 shrink-0 items-center justify-center rounded text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-9"
				:class="canGoEarlier ? '' : 'invisible'"
				title="Earlier months"
				aria-label="Earlier months"
				@click="step(-1)"
			>
				<FeatherIcon name="chevron-left" class="h-5 w-5" />
			</button>
			<div ref="scroller" class="min-w-0 flex-1 overflow-x-auto" @scroll.passive="onScroll" @wheel.passive="onWheel">
				<div :style="{ width: `calc(${Math.max(months.length, 1)} * max(3rem, 100% / ${VISIBLE_MONTHS}))` }">
					<!-- No gap or side padding on the grid: every column is exactly 1/n wide, so the
					     Implementation hours line can put its points at (i + 0.5) / n. -->
					<div
						class="relative grid h-56 items-end border-b border-outline-gray-2"
						:style="{ gridTemplateColumns: `repeat(${Math.max(months.length, 1)}, minmax(0, 1fr))` }"
					>
						<div
							v-for="month in months"
							:key="month.month"
							class="relative flex h-full min-w-0 flex-col justify-end rounded-t px-1"
							:class="month.is_current ? 'bg-surface-gray-1' : ''"
							:title="tooltip(month)"
						>
							<div class="truncate pb-1 text-center text-[10px] font-medium tabular-nums text-ink-gray-6">
								{{ total(month) ? compact(total(month)) : "" }}
							</div>
							<div class="flex flex-col items-center justify-end" :style="{ height: `${barHeight(total(month))}%` }">
								<div
									v-if="estimate(month)"
									class="w-full max-w-8 rounded-t"
									:style="{ height: `${share(estimate(month), month)}%`, ...ESTIMATE_STYLE }"
								/>
								<div
									v-if="confirmed(month)"
									class="w-full max-w-8"
									:class="estimate(month) ? '' : 'rounded-t'"
									:style="{ height: `${share(confirmed(month), month)}%`, ...SUBMITTED_STYLE }"
								/>
							</div>
							<span
								v-if="measure === 'hours' && worked(month) !== null"
								class="pointer-events-none absolute left-1/2 z-10 h-2 w-2 -translate-x-1/2 translate-y-1/2 rounded-full border-2"
								:style="{ bottom: `${barHeight(worked(month))}%`, ...pointStyle(month) }"
							/>
						</div>
						<svg
							v-if="measure === 'hours'"
							class="pointer-events-none absolute inset-0 h-full w-full"
							:viewBox="`0 0 ${months.length} 100`"
							preserveAspectRatio="none"
							aria-hidden="true"
						>
							<polyline :points="linePoints(false)" fill="none" :style="LINE_STYLE" vector-effect="non-scaling-stroke" />
							<polyline
								:points="linePoints(true)"
								fill="none"
								:style="LINE_STYLE"
								stroke-dasharray="4 3"
								vector-effect="non-scaling-stroke"
							/>
						</svg>
					</div>
					<div
						class="grid pt-1"
						:style="{ gridTemplateColumns: `repeat(${Math.max(months.length, 1)}, minmax(0, 1fr))` }"
					>
						<div
							v-for="month in months"
							:key="month.month"
							class="truncate px-1 text-center text-[10px]"
							:class="month.is_current ? 'font-semibold text-ink-gray-9' : month.is_future ? 'italic text-ink-gray-5' : 'text-ink-gray-5'"
						>
							{{ monthLabel(month.month) }}
						</div>
					</div>
				</div>
			</div>
			<button
				type="button"
				class="flex h-56 w-7 shrink-0 items-center justify-center rounded text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-9"
				:class="canGoLater ? '' : 'invisible'"
				title="Later months"
				aria-label="Later months"
				@click="step(1)"
			>
				<FeatherIcon name="chevron-right" class="h-5 w-5" />
			</button>
		</div>

		<div class="mt-3 flex flex-wrap gap-4 text-xs text-ink-gray-6">
			<span class="inline-flex items-center gap-1">
				<i class="inline-block h-2.5 w-2.5 rounded-sm" :style="SUBMITTED_STYLE" />{{ measure === "hours" ? "Capacity (submitted)" : "Submitted contracts" }}
			</span>
			<span class="inline-flex items-center gap-1">
				<i class="inline-block h-2.5 w-2.5 rounded-sm" :style="ESTIMATE_STYLE" />Estimate (drafts)
			</span>
			<template v-if="measure === 'hours'">
				<span class="inline-flex items-center gap-1">
					<i class="inline-block h-2 w-2 rounded-full border-2" :style="SPENT_POINT_STYLE" />Hours spent on Implementations
				</span>
				<span class="inline-flex items-center gap-1">
					<i class="inline-block h-2 w-2 rounded-full border-2" :style="PREDICTED_POINT_STYLE" />Hours predicted
				</span>
			</template>
		</div>
	</section>
</template>

<script setup>
import { call } from "frappe-ui"
import { computed, nextTick, onMounted, ref } from "vue"
import { CONTRACTS_API, formatMoney, formatNumber } from "@spa/contracts/contractFormat.js"

const props = defineProps({
	// { currency, first_month, last_month, months: [{ month, is_current, is_future, fte, cost,
	//   estimate_fte, estimate_cost, capacity_hours, estimate_capacity_hours, spent_hours,
	//   predicted_hours }] }; first_month and last_month bound how far the chart may scroll.
	trend: { type: Object, required: true },
})

const MEASURES = [
	{ value: "cost", label: "Monthly cost" },
	{ value: "fte", label: "FTE" },
	{ value: "hours", label: "Hours" },
]
const measure = ref("cost")

// CSS variables rather than Tailwind classes, like PeriodBars: the bg-ink-* classes are not
// in every cockpit's build. Estimates are the same blue, lighter and dashed, in both themes.
const SUBMITTED_STYLE = { background: "var(--ink-blue-3)" }
const ESTIMATE_STYLE = {
	background: "color-mix(in srgb, var(--ink-blue-3) 35%, transparent)",
	border: "1px dashed var(--ink-blue-3)",
}
// Implementation hours contrast with the blue bars.
const LINE_STYLE = { stroke: "var(--ink-amber-3)", strokeWidth: 2 }
const SPENT_POINT_STYLE = { background: "var(--ink-amber-3)", borderColor: "var(--ink-amber-3)" }
const PREDICTED_POINT_STYLE = { background: "var(--surface-white)", borderColor: "var(--ink-amber-3)" }

// Months that fit the card before it scrolls, and how many to load per request.
const VISIBLE_MONTHS = 12
const PAGE_MONTHS = 12

// Starts with the overview's months; scrolling adds older ones in front and later ones behind.
const months = ref([...(props.trend?.months || [])])
const scroller = ref(null)
const loading = ref("")
const canLoadEarlier = computed(() => !!months.value.length && months.value[0].month > props.trend.first_month)
const canLoadLater = computed(() => !!months.value.length && months.value.at(-1).month < props.trend.last_month)
const atStart = ref(true)
const atEnd = ref(true)
const canGoEarlier = computed(() => !atStart.value || canLoadEarlier.value)
const canGoLater = computed(() => !atEnd.value || canLoadLater.value)

// Scrolling loads only in the direction it moves. Scrolls the chart makes itself (opening on
// the latest months, keeping the view after older months load) set this first, so they
// move nothing and load nothing.
let lastScrollLeft = 0

onMounted(() => {
	// Open on the latest months, so the current one is in view on narrow screens too.
	const el = scroller.value
	el.scrollLeft = el.scrollWidth
	lastScrollLeft = el.scrollLeft
	updateEdges()
})

function columnWidth() {
	return scroller.value.scrollWidth / Math.max(months.value.length, 1)
}
function updateEdges() {
	const el = scroller.value
	atStart.value = el.scrollLeft <= 1
	atEnd.value = el.scrollLeft + el.clientWidth >= el.scrollWidth - 1
}
function onScroll() {
	updateEdges()
	const el = scroller.value
	const delta = el.scrollLeft - lastScrollLeft
	lastScrollLeft = el.scrollLeft
	if (delta < 0 && nearStart(el.scrollLeft)) load("earlier")
	else if (delta > 0 && nearEnd(el.scrollLeft)) load("later")
}
function nearStart(left) {
	return left < 2 * columnWidth()
}
function nearEnd(left) {
	const el = scroller.value
	return left + el.clientWidth > el.scrollWidth - 2 * columnWidth()
}

// A sideways swipe at an edge scrolls nothing, so it fires no scroll event: on a wide card
// all twelve months fit and there is nothing to scroll at all. Load the next page instead.
function onWheel(event) {
	const dx = event.deltaX || (event.shiftKey ? event.deltaY : 0)
	if (!dx || (!event.shiftKey && Math.abs(event.deltaY) > Math.abs(dx))) return
	if (dx < 0 && atStart.value) load("earlier")
	else if (dx > 0 && atEnd.value) load("later")
}

// Half a card per click. Loads the next page first when the scroll would end near the edge
// of the loaded months, so the smooth scroll is not cut short by new columns.
async function step(direction) {
	const distance = (direction * scroller.value.clientWidth) / 2
	const target = scroller.value.scrollLeft + distance
	if (direction < 0 && nearStart(target)) await load("earlier")
	if (direction > 0 && nearEnd(target)) await load("later")
	scroller.value.scrollBy({ left: distance, behavior: "smooth" })
}

async function load(direction) {
	if (loading.value) return
	const earlier = direction === "earlier"
	if (!(earlier ? canLoadEarlier.value : canLoadLater.value)) return
	loading.value = direction
	try {
		const edge = earlier ? months.value[0].month : months.value.at(-1).month
		const range = earlier
			? { first_month: addMonths(edge, -PAGE_MONTHS), last_month: addMonths(edge, -1) }
			: { first_month: addMonths(edge, 1), last_month: addMonths(edge, PAGE_MONTHS) }
		const page = await call(`${CONTRACTS_API}.get_trend`, range)
		const loaded = new Set(months.value.map((m) => m.month))
		const added = (page.months || []).filter((m) => !loaded.has(m.month))
		if (!added.length) return
		if (earlier) {
			// Keep the months in view where they are while new columns appear on the left.
			const el = scroller.value
			const fromRight = el.scrollWidth - el.scrollLeft
			months.value = [...added, ...months.value]
			await nextTick()
			el.scrollLeft = el.scrollWidth - fromRight
			lastScrollLeft = el.scrollLeft
		} else {
			months.value = [...months.value, ...added]
			await nextTick()
		}
		updateEdges()
	} catch {
		// The chart keeps what it has; the arrows stay usable for another try.
	} finally {
		loading.value = ""
	}
}

function addMonths(iso, count) {
	const [year, month] = iso.split("-").map(Number)
	const date = new Date(Date.UTC(year, month - 1 + count, 1))
	return date.toISOString().slice(0, 10)
}
const subtitle = computed(() => {
	if (measure.value === "fte") return "Full-time equivalents in force on the 1st of each month."
	if (measure.value === "hours")
		return "Contract hours per month (weekly hours × 52 / 12) against hours spent and predicted on Implementations."
	return props.trend?.currency
		? `Gross per month in ${props.trend.currency}, at each contract's planning rate.`
		: "Gross per month in company currency."
})

const FIELDS = {
	cost: ["cost", "estimate_cost"],
	fte: ["fte", "estimate_fte"],
	hours: ["capacity_hours", "estimate_capacity_hours"],
}
function confirmed(month) {
	return Number(month[FIELDS[measure.value][0]]) || 0
}
function estimate(month) {
	return Number(month[FIELDS[measure.value][1]]) || 0
}
function total(month) {
	return confirmed(month) + estimate(month)
}
// Hours on Implementations: spent for past months and the current one, predicted for the future.
function worked(month) {
	const value = month.is_future ? month.predicted_hours : month.spent_hours
	return value === null || value === undefined ? null : Number(value) || 0
}

const max = computed(() =>
	Math.max(0, ...months.value.map(total), ...(measure.value === "hours" ? months.value.map((m) => worked(m) || 0) : []))
)

function barHeight(value) {
	return max.value ? Math.max((value / max.value) * 90, value ? 2 : 0) : 0
}
// A part's height within its own bar.
function share(value, month) {
	return total(month) ? (value / total(month)) * 100 : 0
}

// The solid line runs through past months up to the current one; the dashed line starts
// at the current month and runs through the predictions.
function linePoints(future) {
	return months.value
		.map((month, i) => ({ month, i }))
		.filter(({ month }) => worked(month) !== null && (future ? month.is_current || month.is_future : !month.is_future))
		.map(({ month, i }) => `${i + 0.5},${100 - barHeight(worked(month))}`)
		.join(" ")
}
function pointStyle(month) {
	return month.is_future ? PREDICTED_POINT_STYLE : SPENT_POINT_STYLE
}

function format(value) {
	if (measure.value === "cost") return formatMoney(value, props.trend?.currency)
	if (measure.value === "hours") return `${formatNumber(value)} h`
	return formatNumber(value)
}
function compact(value) {
	if (measure.value === "fte") return formatNumber(value)
	if (measure.value === "hours") return `${new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 }).format(value)} h`
	return new Intl.NumberFormat(undefined, {
		notation: "compact",
		maximumFractionDigits: 1,
		...(props.trend?.currency ? { style: "currency", currency: props.trend.currency } : {}),
	}).format(value)
}

function monthLabel(iso) {
	const date = new Date(`${iso}T00:00:00`)
	const month = date.toLocaleDateString(undefined, { month: "short" })
	return date.getMonth() === 0 || iso === months.value[0]?.month ? `${month} ${String(date.getFullYear()).slice(2)}` : month
}

function tooltip(month) {
	const lines = [monthLabel(month.month), `${measure.value === "hours" ? "Capacity" : "Submitted"}: ${format(confirmed(month))}`]
	if (month.is_future) lines.push(`Estimate (drafts): ${format(estimate(month))}`, `Total: ${format(total(month))}`)
	if (measure.value === "hours" && worked(month) !== null) {
		const label = month.is_future ? "Predicted on Implementations" : month.is_current ? "Spent so far on Implementations" : "Spent on Implementations"
		lines.push(`${label}: ${format(worked(month))}`)
	}
	return lines.join("\n")
}
</script>
