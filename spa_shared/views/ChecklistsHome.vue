<template>
	<div class="h-full min-h-0 overflow-y-auto bg-surface-gray-1 p-5">
		<div class="mx-auto flex max-w-7xl flex-col gap-5">
			<div v-if="error" class="rounded-lg border border-outline-gray-2 bg-surface-red-1 p-4 text-sm text-ink-red-4">
				{{ error }}
			</div>
			<div v-else-if="loading" class="flex min-h-64 items-center justify-center text-sm text-ink-gray-5">
				{{ __("Loading checklist dashboard…") }}
			</div>
			<template v-else>
				<section class="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-5">
					<StatCard
						v-for="stat in stats"
						:key="stat.key"
						:label="stat.label"
						:value="stat.value"
						:lines="[
							__('{0} vs previous 90 days', [comparison(stat, 'previous')]),
							__('{0} vs same period last year', [comparison(stat, 'year_ago')]),
						]"
					/>
				</section>

				<PeriodBars
					:title="__('Created and completed')"
					:subtitle="__('Monthly throughput for the last 12 months')"
					:periods="monthlyPeriods"
					:series="[{ label: __('Created') }, { label: __('Completed') }]"
				/>

				<div class="grid grid-cols-1 gap-5 xl:grid-cols-3">
					<HorizontalBars :title="__('Open by status')" :rows="dashboard.status" />
					<HorizontalBars :title="__('Open by owner')" :rows="dashboard.owners" />
					<HorizontalBars :title="__('Aging of open checklists')" :rows="dashboard.aging" />
				</div>
			</template>
		</div>
	</div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue"
import { call } from "frappe-ui"
import HorizontalBars from "@spa/components/dashboard/HorizontalBars.vue"
import PeriodBars from "@spa/components/dashboard/PeriodBars.vue"
import StatCard from "@spa/components/dashboard/StatCard.vue"
import { formatComparison } from "@spa/utils/dashboardFormat.js"
import { __ } from "@spa/utils/i18n.js"
import spaConfig from "@/config"

const loading = ref(true)
const error = ref("")
const dashboard = ref({ windows: {}, monthly: [], status: [], owners: [], aging: [] })

const stats = computed(() => {
	const current = dashboard.value.windows?.current || {}
	return [
		{ key: "created", label: __("Created"), value: current.created ?? 0, kind: "number" },
		{ key: "completed", label: __("Completed"), value: current.completed ?? 0, kind: "number" },
		{ key: "open", label: __("Open now"), value: current.open ?? 0, kind: "level" },
		{
			key: "completion_rate",
			label: __("Completion rate"),
			value: `${current.completion_rate ?? 0}%`,
			kind: "percent",
		},
		{
			key: "median_days",
			label: __("Median completion"),
			value: current.median_days == null ? "—" : __("{0}d", [current.median_days]),
			kind: "days",
		},
	]
})

const monthlyPeriods = computed(() =>
	(dashboard.value.monthly || []).map((month) => ({
		label: month.label,
		values: [month.created, month.completed],
	}))
)

function comparison(stat, windowKey) {
	return formatComparison(
		dashboard.value.windows?.current?.[stat.key],
		dashboard.value.windows?.[windowKey]?.[stat.key],
		stat.kind
	)
}

onMounted(async () => {
	try {
		dashboard.value = await call(`${spaConfig.api}.get_checklist_dashboard`)
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || __("Could not load checklist dashboard")
	} finally {
		loading.value = false
	}
})
</script>
