<template>
	<div class="h-full min-h-0 overflow-y-auto bg-surface-gray-1 p-5">
		<div class="mx-auto flex max-w-7xl flex-col gap-5">
			<div v-if="error" class="rounded-lg border border-outline-gray-2 bg-surface-red-1 p-4 text-sm text-ink-red-4">
				{{ error }}
			</div>
			<div v-else-if="loading" class="flex min-h-64 items-center justify-center text-sm text-ink-gray-5">
				Loading statistics…
			</div>
			<template v-else>
				<p class="text-sm text-ink-gray-6">
					{{ dashboard.company }} · {{ dashboard.currency }} · as of {{ shortDay(dashboard.today) }} (updated every 5 minutes)
				</p>

				<section class="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-6">
					<StatCard
						label="Receipts this month"
						:value="current.receipts_count ?? 0"
						:lines="comparisonLines('receipts_count')"
					/>
					<StatCard
						label="Receipts sum MTD"
						:value="money(current.receipts_sum)"
						:lines="comparisonLines('receipts_sum')"
					/>
					<StatCard
						label="Booked expense MTD"
						:value="money(current.booked)"
						hint="Net, from the general ledger"
						:lines="comparisonLines('booked')"
					/>
					<StatCard
						label="Open to pay"
						:value="money(dashboard.open_to_pay.amount)"
						:hint="pluralize(dashboard.open_to_pay.count, 'approved receipt', 'approved receipts')"
					>
						<button
							v-if="dashboard.open_to_pay.overdue_count"
							type="button"
							class="mt-3 text-left text-xs font-medium text-ink-red-4 hover:underline"
							@click="router.push({ name: 'PaymentsCalendar' })"
						>
							{{ dashboard.open_to_pay.overdue_count }} overdue · {{ money(dashboard.open_to_pay.overdue_amount) }}
						</button>
						<div v-else class="mt-3 text-xs text-ink-gray-6">Nothing overdue</div>
					</StatCard>
					<StatCard
						label="Needs decision"
						:value="dashboard.queue.needs_decision"
						:hint="`${dashboard.queue.inbox} in Inbox`"
						:lines="queueLines"
					/>
					<StatCard label="AI last 30 days" :value="aiValue" :hint="aiHint" :lines="aiLines" />
				</section>

				<PeriodBars
					title="Receipts vs booked expense — 12 months"
					subtitle="Receipts gross by posting date; booked expense net from Purchase Invoices and Journal Entries. Click a month to see its receipts."
					:periods="amountPeriods"
					:series="[{ label: 'Receipts (gross)' }, { label: 'Purchase Invoices (net)' }, { label: 'Journal Entries + Expense Claims (net)' }]"
					:format="(value) => money(value)"
					note="Peak = month far above the usual level; recurring = same month last year within ±20 %."
					selectable
					@select="openMonth"
				/>

				<div class="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
					<PeriodBars
						title="Receipts per month"
						subtitle="Count compared with the same month last year"
						:periods="countPeriods"
						:series="[{ label: 'This year' }, { label: 'Last year' }]"
						selectable
						@select="openMonth"
					/>
					<section class="rounded-lg border border-outline-gray-2 bg-surface-white p-5">
						<h2 class="mb-1 text-base font-semibold text-ink-gray-9">Peaks to address</h2>
						<p class="mb-4 text-sm text-ink-gray-5">Months well above the usual level, with their biggest suppliers.</p>
						<p v-if="!dashboard.peaks.length" class="text-sm text-ink-gray-5">
							No unusual month in the last 12 months.
						</p>
						<ul v-else class="space-y-3">
							<li
								v-for="peak in dashboard.peaks"
								:key="peak.start"
								class="rounded-md border p-3"
								:class="peak.kind === 'peak' ? 'border-outline-red-2 bg-surface-red-1' : 'border-outline-gray-2'"
							>
								<div class="flex flex-wrap items-baseline justify-between gap-2">
									<span class="font-medium text-ink-gray-9">{{ peak.label }}</span>
									<span class="tabular-nums font-semibold text-ink-gray-9">{{ money(peak.value) }}</span>
								</div>
								<div class="mt-1 flex flex-wrap items-center gap-2 text-xs">
									<Badge :theme="peak.kind === 'peak' ? 'red' : 'gray'" :label="peak.kind === 'peak' ? 'Peak' : 'Recurring'" />
									<span class="text-ink-gray-6">{{ peakReason(peak) }}</span>
								</div>
								<ul class="mt-2 space-y-0.5 text-xs text-ink-gray-7">
									<li v-for="supplier in peak.top_suppliers" :key="supplier.supplier" class="flex justify-between gap-2">
										<span class="truncate" :title="supplier.supplier_name">{{ supplier.supplier_name }}</span>
										<span class="tabular-nums">{{ money(supplier.amount) }}</span>
									</li>
								</ul>
								<router-link
									:to="peak.route"
									class="mt-2 inline-block text-xs font-medium text-ink-blue-3 hover:underline"
								>
									Show receipts →
								</router-link>
							</li>
						</ul>
					</section>
				</div>

				<div class="grid grid-cols-1 gap-5 lg:grid-cols-2 xl:grid-cols-3">
					<HorizontalBars
						title="Top suppliers — 12 months"
						:rows="dashboard.top_suppliers"
						:format="(value) => money(value, true)"
						selectable
						empty-text="No receipts in the last 12 months."
						@select="openSupplier"
					/>
					<HorizontalBars
						title="By expense account — 12 months"
						:rows="dashboard.by_expense_account"
						:format="(value) => money(value, true)"
						empty-text="Nothing booked on expense accounts yet."
					/>
					<HorizontalBars
						title="By cost center — 12 months"
						:rows="dashboard.by_cost_center"
						:format="(value) => money(value, true)"
						empty-text="Nothing booked on expense accounts yet."
					/>
					<HorizontalBars
						title="Receipts by status"
						:rows="dashboard.status"
						:format="(value, row) => `${value} · ${money(row.amount, true)}`"
						selectable
						empty-text="No receipts yet."
						@select="(row) => router.push({ path: '/receipts', query: { status: row.key } })"
					/>
					<HorizontalBars
						title="Unpaid approved, by due date"
						:rows="dashboard.aging"
						:format="(value, row) => `${value} · ${money(row.amount, true)}`"
						selectable
						empty-text="Nothing approved and unpaid."
						@select="router.push({ name: 'PaymentsCalendar' })"
					/>
				</div>
			</template>
		</div>
	</div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue"
import { useRouter } from "vue-router"
import { Badge, call } from "frappe-ui"
import HorizontalBars from "@spa/components/dashboard/HorizontalBars.vue"
import PeriodBars from "@spa/components/dashboard/PeriodBars.vue"
import StatCard from "@spa/components/dashboard/StatCard.vue"
import { formatComparison, pluralize } from "@spa/utils/dashboardFormat.js"
import { formatMoney, shortDay } from "../statsFormat"

const STATS_API = "phamos.api.accounting_stats"

const router = useRouter()
const loading = ref(true)
const error = ref("")
const dashboard = ref(null)

const current = computed(() => dashboard.value?.windows?.current || {})

function money(value, compact = false) {
	return formatMoney(value, dashboard.value?.currency, { compact })
}

function comparisonLines(field) {
	const windows = dashboard.value?.windows || {}
	return [
		`${formatComparison(current.value[field], windows.previous_to_date?.[field])} vs ${windows.previous_to_date?.label}`,
		`${formatComparison(current.value[field], windows.avg3?.[field])} vs 3-month avg`,
		`${formatComparison(current.value[field], windows.last_year?.[field])} vs ${windows.last_year?.label}`,
	]
}

const queueLines = computed(() => {
	const queue = dashboard.value?.queue || {}
	if (queue.oldest_days == null) return ["Nothing waiting"]
	return [`Oldest ${queue.oldest_days} d`, `Median age ${queue.median_days} d`]
})

const aiValue = computed(() => {
	const ai = dashboard.value?.ai || {}
	if (!ai.available || ai.auto_ready_share == null) return "—"
	return `${Math.round(ai.auto_ready_share * 100)}%`
})
const aiHint = computed(() =>
	dashboard.value?.ai?.available ? "Ready without a human decision" : "Starts once the AI accountant runs"
)
const aiLines = computed(() => {
	const ai = dashboard.value?.ai || {}
	if (!ai.available) return []
	const lines = [pluralize(ai.runs, "decision", "decisions")]
	if (ai.median_confidence != null) lines.push(`Median confidence ${Math.round(ai.median_confidence * 100)}%`)
	return lines
})

function spikeFooter(month) {
	if (month.mtd) return { footer: "MTD" }
	if (!month.spike) return { footer: null }
	return month.spike.kind === "peak"
		? { footer: "Peak", footerTone: "bad" }
		: { footer: "recurring" }
}

const amountPeriods = computed(() =>
	(dashboard.value?.monthly || []).map((month) => ({
		key: month.start,
		label: month.label,
		start: month.start,
		end: month.end,
		values: [month.receipts_sum, month.booked_pi, month.booked_je],
		...spikeFooter(month),
	}))
)

const countPeriods = computed(() =>
	(dashboard.value?.monthly || []).map((month) => ({
		key: month.start,
		label: month.label,
		start: month.start,
		end: month.end,
		values: [month.receipts_count, month.last_year_count],
		footer: month.mtd ? "MTD" : month.last_year_count ? formatComparison(month.receipts_count, month.last_year_count) : null,
		footerTone:
			month.mtd || !month.last_year_count
				? null
				: month.receipts_count > month.last_year_count * 1.2
					? "bad"
					: null,
	}))
)

function peakReason(peak) {
	const parts = []
	if (peak.avg3) parts.push(`${(peak.value / peak.avg3).toFixed(1)}× the 3-month avg`)
	if (peak.reasons.includes("sigma")) parts.push("far above the year's usual level")
	if (peak.kind === "recurring") parts.push(`last year ${money(peak.last_year, true)}`)
	return parts.join(" · ")
}

function openMonth(period) {
	router.push({ path: "/receipts", query: { from: period.start, to: period.end } })
}

function openSupplier(row) {
	const months = dashboard.value?.monthly || []
	const query = { supplier: row.key }
	if (months.length) Object.assign(query, { from: months[0].start, to: months[months.length - 1].end })
	router.push({ path: "/receipts", query })
}

async function load() {
	try {
		dashboard.value = await call(`${STATS_API}.get_receipt_dashboard`)
		error.value = ""
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not load the statistics"
	} finally {
		loading.value = false
	}
}

onMounted(load)
</script>
