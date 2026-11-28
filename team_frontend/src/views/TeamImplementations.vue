<template>
	<!-- One dense table over the full height; only the table scrolls. Hours only, no amounts. -->
	<div class="flex h-full min-h-0 flex-col gap-3 bg-surface-gray-1 p-4">
		<div v-if="error" class="rounded-lg border border-outline-gray-2 bg-surface-red-1 p-4 text-sm text-ink-red-4">
			{{ error }}
		</div>
		<div v-else-if="loading" class="flex flex-1 items-center justify-center text-sm text-ink-gray-5">
			{{ __("Loading implementations…") }}
		</div>
		<template v-else>
			<KpiStrip :items="kpis" grid-class="grid-cols-2 lg:grid-cols-4" />
			<section class="min-h-0 flex-1 overflow-auto rounded-lg border border-outline-gray-2 bg-surface-white">
				<table class="w-full text-sm">
					<thead class="sticky top-0 z-10 bg-surface-white text-xs text-ink-gray-5">
						<tr>
							<th class="px-3 py-1.5 text-left font-medium">{{ __("Implementation") }}</th>
							<th class="px-3 py-1.5 text-left font-medium">{{ __("Status") }}</th>
							<th class="px-3 py-1.5 text-left font-medium" :title="__('Maturity level, forecast and trend')">{{ __("Health") }}</th>
							<th class="px-3 py-1.5 text-left font-medium">{{ __("Time limit") }}</th>
							<th class="px-3 py-1.5 text-right font-medium" :title="__('Sold · delivered · remaining hours')">{{ __("Sold · delivered · left") }}</th>
							<th class="px-3 py-1.5 text-left font-medium" :title="__('Actual hours per month; the line is the predicted hours per month')">{{ __("Last 6 months") }}</th>
							<th class="px-3 py-1.5 text-left font-medium">{{ __("Modules") }}</th>
						</tr>
					</thead>
					<tbody>
						<tr v-if="!rows.length">
							<td colspan="7" class="px-3 py-3 text-ink-gray-5">{{ __("No open implementation belongs to this team.") }}</td>
						</tr>
						<tr v-for="row in rows" :key="row.name" class="border-t border-outline-gray-1 align-middle">
							<td class="max-w-56 px-3 py-1.5">
								<a :href="`/app/implementation/${encodeURIComponent(row.name)}`" target="_blank" class="block truncate font-medium text-ink-gray-9 hover:underline">
									{{ row.name }}
								</a>
								<div class="truncate text-xs text-ink-gray-5">{{ row.customer }}</div>
							</td>
							<td class="px-3 py-1.5 text-ink-gray-7">{{ __(row.status) }}</td>
							<td class="whitespace-nowrap px-3 py-1.5 text-ink-gray-7">
								<span :title="row.maturity_level">{{ maturity(row) }}</span>
								<span class="ml-2" :title="row.forecast">{{ forecastIcon(row) }}</span>
								<span class="ml-2 text-xs" :class="trendClass(row.trend)">{{ row.trend ? __(row.trend) : "" }}</span>
							</td>
							<td class="min-w-36 px-3 py-1.5">
								<template v-if="row.enable_time_limit && row.limit_hours">
									<div class="h-1.5 overflow-hidden rounded bg-surface-gray-3">
										<div class="h-full rounded" :class="limitClass(row)" :style="{ width: `${Math.min(100, row.time_limit_percent_used || 0)}%` }" />
									</div>
									<div class="mt-0.5 text-xs tabular-nums text-ink-gray-6">
										{{ __("{0} of {1} h", [hours(row.hours_used_this_period), hours(row.limit_hours)]) }}
									</div>
								</template>
								<span v-else class="text-xs text-ink-gray-5">{{ __("No limit") }}</span>
							</td>
							<td class="whitespace-nowrap px-3 py-1.5 text-right tabular-nums text-ink-gray-7">
								{{ hours(row.sales_order_total_hrs) }} · {{ hours(row.delivered_total_hrs) }} · {{ hours(row.remaining_hrs) }}
							</td>
							<td class="px-3 py-1.5">
								<div class="relative flex h-8 items-end gap-0.5" :title="sparkTitle(row)">
									<div
										v-for="month in row.months"
										:key="month.label"
										class="w-3 rounded-sm bg-ink-blue-3"
										:style="{ height: `${barHeight(month.hours, row)}%` }"
									/>
									<div
										v-if="row.predicted_per_month"
										class="pointer-events-none absolute inset-x-0 border-t border-dashed border-ink-amber-3"
										:style="{ bottom: `${barHeight(row.predicted_per_month, row)}%` }"
									/>
								</div>
							</td>
							<td class="px-3 py-1.5 text-xs text-ink-gray-6">
								<span v-if="!row.modules.length">—</span>
								<span v-else :title="moduleTitle(row)">{{ moduleSummary(row) }}</span>
							</td>
						</tr>
					</tbody>
				</table>
			</section>
		</template>
	</div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue"
import { call } from "frappe-ui"
import KpiStrip from "@spa/components/dashboard/KpiStrip.vue"
import { __ } from "@spa/utils/i18n.js"
import spaConfig from "../config"

const loading = ref(true)
const error = ref("")
const rows = ref([])

function hours(value) {
	if (value == null) return "—"
	return Number(value).toLocaleString(undefined, { maximumFractionDigits: 0 })
}

function maturity(row) {
	const level = (row.maturity_level || "").split(" ")[0]
	return level ? __("Level {0}", [level]) : "—"
}

function forecastIcon(row) {
	// "1 ☀️ - alles gut…": the symbol after the number
	return (row.forecast || "").split(" ")[1] || ""
}

function trendClass(trend) {
	if (trend === "Improving") return "text-ink-green-3"
	if (trend === "Declining") return "text-ink-red-4"
	return "text-ink-gray-5"
}

function limitClass(row) {
	const used = row.time_limit_percent_used || 0
	if (used >= 100) return "bg-ink-red-4"
	if (used >= 80) return "bg-ink-amber-3"
	return "bg-ink-green-3"
}

function barHeight(value, row) {
	const max = Math.max(1, row.predicted_per_month || 0, ...row.months.map((m) => m.hours))
	return value ? Math.max(4, (value / max) * 100) : 0
}

function sparkTitle(row) {
	const months = row.months.map((m) => `${m.label}: ${hours(m.hours)} h`).join("\n")
	return row.predicted_per_month ? `${months}\n${__("Predicted: {0} h per month", [hours(row.predicted_per_month)])}` : months
}

function moduleSummary(row) {
	const reached = row.modules.filter((m) => m.target_level && m.current_level >= m.target_level).length
	return __("{0} of {1} at target", [reached, row.modules.length])
}

function moduleTitle(row) {
	return row.modules.map((m) => `${m.module}: ${m.current_level ?? 0} / ${m.target_level ?? "—"}`).join("\n")
}

const kpis = computed(() => {
	const limited = rows.value.filter((r) => r.enable_time_limit && r.limit_hours)
	const overLimit = limited.filter((r) => (r.time_limit_percent_used || 0) >= 100).length
	const lastMonth = rows.value.reduce((sum, r) => sum + (r.months.at(-1)?.hours || 0), 0)
	const predicted = rows.value.reduce((sum, r) => sum + (r.predicted_per_month || 0), 0)
	return [
		{ label: __("Open implementations"), value: rows.value.length },
		{ label: __("Over their time limit"), value: overLimit, hint: __("of {0} with a limit", [limited.length]) },
		{ label: __("Hours this month"), value: hours(lastMonth), hint: __("so far, all implementations") },
		{ label: __("Predicted per month"), value: hours(predicted), hint: __("from the 3-month prediction") },
	]
})

async function load() {
	loading.value = true
	error.value = ""
	try {
		const data = await call(`${spaConfig.api}.get_team_implementations`)
		rows.value = data.implementations || []
	} catch (e) {
		error.value = e.messages?.[0] || e.message || __("Could not load the implementations.")
	} finally {
		loading.value = false
	}
}

onMounted(load)
</script>
