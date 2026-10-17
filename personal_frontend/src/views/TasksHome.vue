<template>
	<div class="h-full min-h-0 overflow-y-auto bg-surface-gray-1 p-5">
		<div class="mx-auto flex max-w-7xl flex-col gap-5">
			<div v-if="error" class="rounded-lg border border-outline-gray-2 bg-surface-red-1 p-4 text-sm text-ink-red-4">{{ error }}</div>
			<div v-else-if="loading" class="flex min-h-64 items-center justify-center text-sm text-ink-gray-5">Loading your Tasks…</div>
			<template v-else>
				<section class="grid grid-cols-1 gap-3 md:grid-cols-2" :class="data.hours ? 'xl:grid-cols-5' : 'xl:grid-cols-4'">
					<RouterLink v-for="stat in stats" :key="stat.key" :to="{ name: 'TasksGantt' }" class="rounded-lg focus-visible:outline focus-visible:outline-2 focus-visible:outline-outline-gray-4">
						<StatCard :label="stat.label" :value="stat.value" :hint="stat.hint" class="h-full hover:border-outline-gray-3" />
					</RouterLink>
					<StatCard
						v-if="data.hours"
						label="My hours this week"
						:value="hours(data.hours.week)"
						:lines="[`Today ${hours(data.hours.today)}`, `This month ${hours(data.hours.month)}`]"
					/>
				</section>

				<div class="grid grid-cols-1 gap-5 xl:grid-cols-3">
					<section class="rounded-lg border border-outline-gray-2 bg-surface-white p-5 xl:col-span-2">
						<h2 class="mb-3 text-base font-semibold text-ink-gray-9">Next due</h2>
						<p v-if="!data.next_due.length" class="text-sm text-ink-gray-5">No open Task has an end date.</p>
						<ul v-else class="divide-y divide-outline-gray-1">
							<li v-for="task in data.next_due" :key="task.name">
								<RouterLink
									:to="{ name: 'TaskDetail', params: { name: task.name } }"
									data-list-item
									class="flex items-center gap-3 py-2 text-sm hover:bg-surface-gray-1 focus:outline-none focus-visible:bg-surface-gray-2"
								>
									<span class="w-28 flex-none whitespace-nowrap text-xs text-ink-gray-5">{{ task.name }}</span>
									<span class="min-w-0 flex-1 truncate text-ink-gray-8">{{ task.subject }}</span>
									<span class="flex-none text-xs tabular-nums" :class="task.overdue ? 'font-medium text-ink-red-4' : 'text-ink-gray-6'">
										{{ task.overdue ? "overdue · " : "" }}{{ formatDate(task.exp_end_date) }}
									</span>
								</RouterLink>
							</li>
						</ul>
					</section>
					<HorizontalBars title="Open by status" :rows="data.by_status" empty-text="No open Tasks." />
				</div>

				<HorizontalBars
					title="Time used of the estimate"
					:rows="data.effort"
					:format="(value, row) => `${hours(row.actual)} of ${hours(row.expected)} · ${value} %`"
					empty-text="None of your open Tasks has an expected time."
					selectable
					@select="(row) => router.push({ name: 'TaskDetail', params: { name: row.name } })"
				/>
			</template>
		</div>
	</div>
</template>

<script setup>
// My Tasks at a glance (#1604): what is overdue or due soon, what I finished, my hours from the
// timesheet timer, and which Tasks use more time than estimated.
import { computed, onMounted, ref } from "vue"
import { useRouter } from "vue-router"
import { call } from "frappe-ui"
import HorizontalBars from "@spa/components/dashboard/HorizontalBars.vue"
import StatCard from "@spa/components/dashboard/StatCard.vue"
import { useUserRealtime } from "@spa/composables/useUserRealtime.js"
import { formatDate } from "@spa/utils/datetime.js"
import spaConfig from "@/config"

const router = useRouter()
const loading = ref(true)
const error = ref("")
const data = ref({ totals: {}, hours: null, by_status: [], next_due: [], effort: [], recent_days: 7, due_soon_days: 7 })

// Decimal hours as "3 h 30 min"; whole hours without minutes.
function hours(value) {
	const minutes = Math.round((Number(value) || 0) * 60)
	const h = Math.floor(minutes / 60)
	const m = minutes % 60
	if (!h) return `${m} min`
	return m ? `${h} h ${m} min` : `${h} h`
}

const stats = computed(() => {
	const t = data.value.totals || {}
	return [
		{ key: "overdue", label: "Overdue", value: t.overdue ?? 0, hint: "Past the expected end date" },
		{ key: "due_soon", label: "Due soon", value: t.due_soon ?? 0, hint: `In the next ${data.value.due_soon_days} days` },
		{ key: "open", label: "Open now", value: t.open ?? 0, hint: "Assigned to me" },
		{ key: "completed", label: "Completed", value: t.completed_recently ?? 0, hint: `In the last ${data.value.recent_days} days` },
	]
})

async function load() {
	try {
		data.value = await call(`${spaConfig.api}.get_task_dashboard`)
		error.value = ""
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not load your Tasks"
	} finally {
		loading.value = false
	}
}

useUserRealtime("cockpit_todos_changed", load, { debounceMs: 500 })
useUserRealtime("cockpit_timer_changed", load, { debounceMs: 500 })
onMounted(load)
</script>
