<template>
	<!-- Sales Orders: the /timesheet "Sales Orders" tab for the open implementation (hours only). -->
	<div class="h-full min-h-0 overflow-y-auto bg-surface-gray-1 p-5">
		<div class="mx-auto flex max-w-7xl flex-col gap-5">
			<div v-if="error" class="rounded-lg border border-outline-gray-2 bg-surface-red-1 p-4 text-sm text-ink-red-4">
				{{ error }}
			</div>

			<section class="grid grid-cols-2 gap-3 xl:grid-cols-4">
				<StatCard
					:label="__('Ordered')"
					:value="hours(summary?.total_so_hrs)"
					:hint="summary ? __('{0} sales orders, {1} open', [summary.total_so_count, summary.open_so_count]) : ''"
				/>
				<StatCard :label="__('Delivered')" :value="hours(summary?.delivered_hrs)" :hint="__('on delivery notes')" />
				<StatCard :label="__('Booked, not yet delivered')" :value="hours(summary?.timesheet_hrs)" :hint="__('billable timesheet hours')" />
				<StatCard :label="__('Remaining')" :value="hours(summary?.remaining_hrs)" :hint="__('ordered minus delivered and booked')" />
			</section>

			<section v-if="summary && summary.total_so_hrs > 0" class="rounded-lg border border-outline-gray-2 bg-surface-white p-4">
				<div class="text-xs font-medium uppercase tracking-wide text-ink-gray-5">{{ __("Ordered hours") }}</div>
				<div class="mt-3 flex h-3 overflow-hidden rounded-full bg-surface-gray-2" role="img" :aria-label="barLabel">
					<div :style="{ width: share(summary.delivered_hrs), background: 'var(--ink-blue-3)' }" />
					<div :style="{ width: share(summary.timesheet_hrs), background: 'var(--ink-amber-3)' }" />
				</div>
				<div class="mt-2 flex flex-wrap gap-4 text-xs text-ink-gray-6">
					<span class="flex items-center gap-1.5"><span class="h-2 w-2 rounded-full" style="background: var(--ink-blue-3)" />{{ __("Delivered") }}</span>
					<span class="flex items-center gap-1.5"><span class="h-2 w-2 rounded-full" style="background: var(--ink-amber-3)" />{{ __("Booked, not yet delivered") }}</span>
					<span class="flex items-center gap-1.5"><span class="h-2 w-2 rounded-full bg-surface-gray-3" />{{ __("Remaining") }}</span>
				</div>
			</section>

			<section class="overflow-hidden rounded-lg border border-outline-gray-2 bg-surface-white">
				<div class="flex flex-wrap items-center gap-2 border-b border-outline-gray-2 px-4 py-2.5">
					<FormControl v-model="search" type="text" size="sm" :placeholder="__('Search')" class="w-56" />
					<FormControl v-model="status" type="select" size="sm" class="w-48" :options="statusOptions" />
					<Button v-if="search || status" variant="ghost" size="sm" @click="clearFilters">{{ __("Reset filters") }}</Button>
				</div>
				<div class="overflow-x-auto">
					<div class="min-w-[880px]">
						<div :class="[GRID, 'border-b border-outline-gray-2 bg-surface-gray-1 py-2 text-xs font-medium text-ink-gray-5']">
							<button
								v-for="col in COLUMNS"
								:key="col.key"
								type="button"
								class="flex min-w-0 items-center gap-1 text-left hover:text-ink-gray-8"
								:class="col.align === 'right' ? 'justify-end' : ''"
								@click="sortBy(col.key)"
							>
								<span class="truncate">{{ __(col.label) }}</span>
								<FeatherIcon v-if="sort.key === col.key" :name="sort.asc ? 'arrow-up' : 'arrow-down'" class="h-3 w-3 flex-shrink-0" />
							</button>
						</div>
						<div
							v-for="so in visible"
							:key="so.name"
							:class="[GRID, 'border-b border-outline-gray-1 py-2.5 text-sm hover:bg-surface-gray-1']"
						>
							<span class="truncate text-xs font-semibold text-ink-gray-6">{{ so.name }}</span>
							<span class="tabular-nums text-ink-gray-7">{{ date(so.transaction_date) }}</span>
							<span class="tabular-nums text-ink-gray-7">{{ date(so.delivery_date) }}</span>
							<span>
								<span class="inline-flex h-5 items-center rounded-full px-1.5 text-xs font-semibold" :class="statusClass(so.status)">
									{{ __(so.status) }}
								</span>
							</span>
							<span class="text-right tabular-nums text-ink-gray-8">{{ hours(so.total_hrs) }}</span>
							<span class="text-right tabular-nums text-ink-gray-8">{{ hours(so.delivered_hrs) }}</span>
							<span class="text-right tabular-nums text-ink-gray-8">{{ hours(so.remaining_hrs) }}</span>
							<span class="flex items-center gap-2">
								<span class="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-gray-2">
									<span class="block h-full rounded-full" :style="{ width: `${Math.min(progress(so), 100)}%`, background: 'var(--ink-gray-7)' }" />
								</span>
								<span class="w-10 text-right text-xs tabular-nums text-ink-gray-6">{{ progress(so) }}%</span>
							</span>
						</div>
						<div v-if="!loading && !filtered.length" class="px-4 py-8 text-center text-sm text-ink-gray-5">
							{{ orders.length ? __("No sales orders match the filters.") : __("No sales orders for this implementation yet.") }}
						</div>
						<div v-if="loading" class="px-4 py-8 text-center text-sm text-ink-gray-5">{{ __("Loading…") }}</div>
					</div>
				</div>
				<div class="flex items-center gap-3 border-t border-outline-gray-2 px-4 py-2.5 text-xs text-ink-gray-6">
					<span>{{ __("Showing {0} of {1}", [visible.length, filtered.length]) }}</span>
					<Button v-if="visible.length < filtered.length" class="ml-auto" size="sm" @click="limit += PAGE">{{ __("Load more") }}</Button>
				</div>
			</section>
		</div>
	</div>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import dayjs from "dayjs"
import { call } from "frappe-ui"
import StatCard from "@spa/components/dashboard/StatCard.vue"
import { __ } from "@spa/utils/i18n.js"
import spaConfig from "../config"

const props = defineProps({ implementation: { type: String, required: true } })

const PAGE = 20
const GRID =
	"grid grid-cols-[minmax(0,1fr)_6.5rem_6.5rem_9rem_5rem_5.5rem_5.5rem_minmax(8rem,1fr)] items-center gap-x-4 px-4"
const COLUMNS = [
	{ key: "name", label: "Sales order" },
	{ key: "transaction_date", label: "Ordered on" },
	{ key: "delivery_date", label: "Delivery" },
	{ key: "status", label: "Status" },
	{ key: "total_hrs", label: "Hours", align: "right" },
	{ key: "delivered_hrs", label: "Delivered", align: "right" },
	{ key: "remaining_hrs", label: "Remaining", align: "right" },
	{ key: "progress", label: "Progress" },
]
const STATUSES = ["To Deliver and Bill", "To Bill", "To Deliver", "Completed", "Closed", "On Hold"]

const orders = ref([])
const summary = ref(null)
const loading = ref(false)
const error = ref("")
const search = ref("")
const status = ref("")
const sort = ref({ key: "transaction_date", asc: false })
const limit = ref(PAGE)

const statusOptions = computed(() => [{ label: __("All statuses"), value: "" }, ...STATUSES.map((s) => ({ label: __(s), value: s }))])

const filtered = computed(() => {
	const q = search.value.trim().toLowerCase()
	const rows = orders.value.filter(
		(so) => (!status.value || so.status === status.value) && (!q || `${so.name} ${so.status}`.toLowerCase().includes(q))
	)
	const { key, asc } = sort.value
	const value = (so) => (key === "progress" ? progress(so) : so[key] ?? "")
	return [...rows].sort((a, b) => {
		const x = value(a)
		const y = value(b)
		const cmp = typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y))
		return asc ? cmp : -cmp
	})
})
const visible = computed(() => filtered.value.slice(0, limit.value))
const barLabel = computed(() =>
	summary.value
		? __("Delivered {0}, booked {1}, remaining {2}", [
				hours(summary.value.delivered_hrs),
				hours(summary.value.timesheet_hrs),
				hours(summary.value.remaining_hrs),
			])
		: ""
)

watch(() => props.implementation, load, { immediate: true })
watch([search, status], () => (limit.value = PAGE))

async function load() {
	loading.value = true
	error.value = ""
	orders.value = []
	summary.value = null
	try {
		const data = await call(`${spaConfig.api}.get_sales_orders`, { implementation: props.implementation })
		orders.value = data?.sales_orders || []
		summary.value = data?.summary || null
	} catch (e) {
		error.value = e?.message || __("Could not load the sales orders")
	} finally {
		loading.value = false
	}
}

function sortBy(key) {
	sort.value = sort.value.key === key ? { key, asc: !sort.value.asc } : { key, asc: true }
}

function clearFilters() {
	search.value = ""
	status.value = ""
}

function progress(so) {
	return so.total_hrs > 0 ? Math.round((so.delivered_hrs / so.total_hrs) * 1000) / 10 : 0
}

function share(value) {
	const total = summary.value?.total_so_hrs || 0
	return total > 0 ? `${Math.max(0, Math.min(100, (value / total) * 100))}%` : "0%"
}

function hours(value) {
	if (value == null) return "—"
	return `${Math.round(Number(value) * 10) / 10} h`
}

function date(value) {
	return value ? dayjs(value).format("D MMM YYYY") : "—"
}

function statusClass(value) {
	if (value === "Completed") return "bg-surface-green-2 text-ink-green-3"
	if (value === "Closed") return "bg-surface-gray-2 text-ink-gray-6"
	if (value === "On Hold") return "bg-surface-amber-2 text-ink-amber-3"
	return "bg-surface-blue-2 text-ink-blue-3"
}
</script>
