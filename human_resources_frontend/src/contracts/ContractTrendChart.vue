<template>
	<section class="rounded-lg border border-outline-gray-2 bg-surface-white p-5">
		<div class="mb-4 flex flex-wrap items-start justify-between gap-3">
			<div>
				<h2 class="text-base font-semibold text-ink-gray-9">Development per month</h2>
				<p class="text-sm text-ink-gray-5">
					{{ measure === "cost" ? costSubtitle : "Full-time equivalents in force on the 1st of each month." }}
					The next {{ futureCount }} months add draft contracts as an estimate.
				</p>
			</div>
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

		<!-- On narrow screens the bars scroll inside the card, never the page. -->
		<div class="overflow-x-auto">
			<div
				class="grid h-56 min-w-[36rem] items-end gap-2 border-b border-outline-gray-2 px-1"
				:style="{ gridTemplateColumns: `repeat(${Math.max(months.length, 1)}, minmax(0, 1fr))` }"
			>
				<div
					v-for="month in months"
					:key="month.month"
					class="flex h-full min-w-0 flex-col justify-end rounded-t"
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
				</div>
			</div>
			<div
				class="grid min-w-[36rem] gap-2 px-1 pt-1"
				:style="{ gridTemplateColumns: `repeat(${Math.max(months.length, 1)}, minmax(0, 1fr))` }"
			>
				<div
					v-for="month in months"
					:key="month.month"
					class="truncate text-center text-[10px]"
					:class="month.is_current ? 'font-semibold text-ink-gray-9' : month.is_future ? 'italic text-ink-gray-5' : 'text-ink-gray-5'"
				>
					{{ monthLabel(month.month) }}
				</div>
			</div>
		</div>

		<div class="mt-3 flex flex-wrap gap-4 text-xs text-ink-gray-6">
			<span class="inline-flex items-center gap-1"><i class="inline-block h-2.5 w-2.5 rounded-sm" :style="SUBMITTED_STYLE" />Submitted contracts</span>
			<span class="inline-flex items-center gap-1">
				<i class="inline-block h-2.5 w-2.5 rounded-sm" :style="ESTIMATE_STYLE" />Estimate (drafts)
			</span>
		</div>
	</section>
</template>

<script setup>
import { computed, ref } from "vue"
import { formatMoney, formatNumber } from "@spa/contracts/contractFormat.js"

const props = defineProps({
	// { currency, months: [{ month, is_current, is_future, fte, cost, estimate_fte, estimate_cost }] }
	trend: { type: Object, required: true },
})

const MEASURES = [
	{ value: "cost", label: "Monthly cost" },
	{ value: "fte", label: "FTE" },
]
const measure = ref("cost")

// CSS variables rather than Tailwind classes, like PeriodBars: the bg-ink-* classes are not
// in every cockpit's build. Estimates are the same blue, lighter and dashed, in both themes.
const SUBMITTED_STYLE = { background: "var(--ink-blue-3)" }
const ESTIMATE_STYLE = {
	background: "color-mix(in srgb, var(--ink-blue-3) 35%, transparent)",
	border: "1px dashed var(--ink-blue-3)",
}

const months = computed(() => props.trend?.months || [])
const futureCount = computed(() => months.value.filter((m) => m.is_future).length)
const costSubtitle = computed(() =>
	props.trend?.currency
		? `Gross per month in ${props.trend.currency}, at each contract's planning rate.`
		: "Gross per month in company currency."
)

function confirmed(month) {
	return Number(measure.value === "cost" ? month.cost : month.fte) || 0
}
function estimate(month) {
	return Number(measure.value === "cost" ? month.estimate_cost : month.estimate_fte) || 0
}
function total(month) {
	return confirmed(month) + estimate(month)
}

const max = computed(() => Math.max(0, ...months.value.map(total)))

function barHeight(value) {
	return max.value ? Math.max((value / max.value) * 90, value ? 2 : 0) : 0
}
// A part's height within its own bar.
function share(value, month) {
	return total(month) ? (value / total(month)) * 100 : 0
}

function format(value) {
	return measure.value === "cost" ? formatMoney(value, props.trend?.currency) : formatNumber(value)
}
function compact(value) {
	if (measure.value === "fte") return formatNumber(value)
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
	const lines = [monthLabel(month.month), `Submitted: ${format(confirmed(month))}`]
	if (month.is_future) lines.push(`Estimate (drafts): ${format(estimate(month))}`, `Total: ${format(total(month))}`)
	return lines.join("\n")
}
</script>
