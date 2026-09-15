<template>
	<div class="min-h-0 flex-1 overflow-y-auto bg-surface-gray-1 p-5">
		<div class="mx-auto flex max-w-7xl flex-col gap-5">
			<div v-if="error" class="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
				{{ error }}
			</div>
			<div v-else-if="loading" class="flex min-h-64 items-center justify-center text-sm text-ink-gray-5">
				Loading lead dashboard…
			</div>
			<template v-else>
				<section class="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
					<div
						v-for="stat in stats"
						:key="stat.key"
						class="rounded-lg border border-outline-gray-2 bg-surface-white p-4"
						:class="stat.highlight ? 'border-amber-300 bg-amber-50' : ''"
					>
						<div class="text-xs font-medium uppercase tracking-wide text-ink-gray-5">
							{{ stat.label }}
						</div>
						<div class="mt-2 text-2xl font-semibold tabular-nums text-ink-gray-9">
							{{ stat.value }}
						</div>
						<div v-if="stat.comparison" class="mt-3 space-y-1 text-xs text-ink-gray-6">
							<div>{{ stat.comparison }}</div>
						</div>
					</div>
				</section>

				<section class="rounded-lg border border-outline-gray-2 bg-surface-white p-5">
					<div class="mb-4">
						<h2 class="text-base font-semibold text-ink-gray-9">Created, converted, lost</h2>
						<p class="text-sm text-ink-gray-5">Monthly throughput for the last 12 months</p>
					</div>
					<div class="grid h-56 grid-cols-12 items-end gap-2 border-b border-outline-gray-2 px-2">
						<div
							v-for="month in dashboard.monthly"
							:key="month.label"
							class="flex h-full min-w-0 flex-col justify-end gap-1"
						>
							<div class="flex flex-1 items-end justify-center gap-1">
								<div
									class="w-2 rounded-t bg-blue-400"
									:style="{ height: `${barHeight(month.created, monthlyMax)}%` }"
									:title="`${month.created} created`"
								/>
								<div
									class="w-2 rounded-t bg-green-500"
									:style="{ height: `${barHeight(month.converted, monthlyMax)}%` }"
									:title="`${month.converted} converted`"
								/>
								<div
									class="w-2 rounded-t bg-gray-400"
									:style="{ height: `${barHeight(month.lost, monthlyMax)}%` }"
									:title="`${month.lost} lost`"
								/>
							</div>
							<div class="truncate pb-2 text-center text-[10px] text-ink-gray-5">{{ month.label }}</div>
						</div>
					</div>
					<div class="mt-3 flex gap-4 text-xs text-ink-gray-6">
						<span><i class="mr-1 inline-block h-2.5 w-2.5 rounded-sm bg-blue-400" />Created</span>
						<span><i class="mr-1 inline-block h-2.5 w-2.5 rounded-sm bg-green-500" />Converted</span>
						<span><i class="mr-1 inline-block h-2.5 w-2.5 rounded-sm bg-gray-400" />Lost</span>
					</div>
				</section>

				<div class="grid grid-cols-1 gap-5 xl:grid-cols-3">
					<DashboardBars title="By status" :rows="dashboard.status" />
					<DashboardBars title="By owner (open)" :rows="dashboard.owners" />
					<DashboardBars title="Follow-up aging (open)" :rows="dashboard.follow_up" />
				</div>
			</template>
		</div>
	</div>
</template>

<script setup>
import { computed, defineComponent, h, onMounted, ref } from "vue"
import { call } from "frappe-ui"

const API = "phamos.api.sales_leads"

const loading = ref(true)
const error = ref("")
const dashboard = ref({
	windows: {},
	open_pipeline: 0,
	monthly: [],
	status: [],
	owners: [],
	follow_up: [],
})

const DashboardBars = defineComponent({
	props: {
		title: { type: String, required: true },
		rows: { type: Array, default: () => [] },
	},
	setup(props) {
		return () => {
			const max = Math.max(1, ...props.rows.map((row) => Number(row.value) || 0))
			return h("section", { class: "rounded-lg border border-outline-gray-2 bg-surface-white p-5" }, [
				h("h2", { class: "mb-4 text-base font-semibold text-ink-gray-9" }, props.title),
				h(
					"div",
					{ class: "space-y-3" },
					props.rows.map((row) =>
						h("div", { key: row.label }, [
							h("div", { class: "mb-1 flex justify-between gap-3 text-xs" }, [
								h("span", { class: "truncate text-ink-gray-7" }, row.label),
								h("span", { class: "font-semibold tabular-nums text-ink-gray-9" }, String(row.value)),
							]),
							h("div", { class: "h-2 overflow-hidden rounded-full bg-surface-gray-2" }, [
								h("div", {
									class: "h-full rounded-full bg-blue-500",
									style: { width: `${(Number(row.value) / max) * 100}%` },
								}),
							]),
						])
					)
				),
			])
		}
	},
})

const followUpBacklog = computed(() => {
	const rows = dashboard.value.follow_up || []
	const noDate = rows.find((r) => r.label === "No date set")?.value || 0
	const overdue = rows.find((r) => r.label === "Overdue")?.value || 0
	return noDate + overdue
})

const stats = computed(() => {
	const current = dashboard.value.windows?.current || {}
	return [
		{ key: "backlog", label: "Follow-up backlog", value: followUpBacklog.value, highlight: true },
		{ key: "open", label: "Open pipeline", value: dashboard.value.open_pipeline ?? 0 },
		{ key: "created", label: "New leads (90d)", value: current.created ?? 0 },
		{ key: "converted", label: "Converted (90d)", value: current.converted ?? 0 },
	]
})

function barHeight(value, max) {
	if (!value) return 0
	return Math.max(4, (Number(value) / Number(max || 1)) * 100)
}

const monthlyMax = computed(() =>
	Math.max(1, ...dashboard.value.monthly.flatMap((month) => [month.created, month.converted, month.lost]))
)

onMounted(async () => {
	try {
		dashboard.value = await call(`${API}.get_lead_dashboard`)
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not load lead dashboard"
	} finally {
		loading.value = false
	}
})
</script>
