<template>
	<div class="h-full w-full overflow-y-auto px-6 py-6">
		<div class="mb-6 flex flex-wrap items-center justify-between gap-3">
			<div>
				<div class="flex items-center gap-2">
					<button
						class="rounded-md px-2 py-1 text-sm text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800"
						@click="backToQueue"
					>
						← Back to queue
					</button>
					<a
						v-if="detail?.desk_url"
						:href="detail.desk_url"
						class="rounded-md px-2 py-1 text-sm text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800"
					>
						Open in Desk
					</a>
				</div>
				<h2 class="mt-2 text-xl font-semibold text-gray-900 dark:text-gray-100">{{ route.params.name }}</h2>
				<p v-if="detail" class="mt-1 text-sm text-gray-500 dark:text-gray-400">
					{{ detail.maturity_group_title || detail.maturity_label || "—" }} ·
					Account Manager: {{ detail.owner_name || "—" }} · {{ detail.customer || "No customer" }}
				</p>
			</div>
			<div v-if="detail" class="flex items-center gap-2">
				<span
					class="inline-flex rounded-full px-2.5 py-1 text-xs font-medium"
					:class="detail.reviewed_today ? 'bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300' : 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300'"
				>
					{{ detail.reviewed_today ? "Reviewed today" : "Pending review" }}
				</span>
				<span class="text-xs text-gray-500 dark:text-gray-400">{{ queuePositionLabel }}</span>
			</div>
		</div>

		<div v-if="loading" class="text-sm text-gray-500 dark:text-gray-400">Loading implementation…</div>
		<div v-else-if="error" class="text-sm text-red-600 dark:text-red-400">{{ error }}</div>

		<div v-else-if="detail" :key="route.params.name" class="grid gap-6 xl:grid-cols-5">
			<section class="space-y-6 xl:col-span-3">
				<div class="rounded-xl border border-gray-200 bg-white p-5 dark:border-gray-800 dark:bg-gray-900">
					<h3 class="mb-4 text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Weekly update</h3>
					<ImplementationReviewForm v-model="formValues" :options="detail.options || {}" />
					<div class="mt-6 border-t border-gray-100 pt-6 dark:border-gray-800">
						<PredictionMonthEditor v-model="predictions" />
						<p class="mt-2 text-xs text-gray-500 dark:text-gray-400">
							Predicted next 3 months total: {{ formatHours(detail.stats?.predicted_time_next_3_months) }} (recomputed on save)
						</p>
					</div>
				</div>

				<div class="flex flex-wrap items-center gap-2">
					<Button variant="solid" :loading="saving" @click="save(false)">Save</Button>
					<Button variant="solid" :loading="saving" @click="save(true)">Save &amp; next</Button>
					<Button :disabled="saving" @click="skip">Skip</Button>
				</div>
			</section>

			<section class="space-y-6 xl:col-span-2">
				<div class="rounded-xl border border-gray-200 bg-white p-5 dark:border-gray-800 dark:bg-gray-900">
					<h3 class="mb-4 text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Context</h3>
					<div class="grid gap-4 sm:grid-cols-2">
						<div>
							<div class="text-xs text-gray-500 dark:text-gray-400">Department</div>
							<div class="text-sm font-medium text-gray-900 dark:text-gray-100">{{ detail.department || "—" }}</div>
						</div>
						<div>
							<div class="text-xs text-gray-500 dark:text-gray-400">Team</div>
							<div class="text-sm font-medium text-gray-900 dark:text-gray-100">{{ detail.team || "—" }}</div>
						</div>
						<div>
							<div class="text-xs text-gray-500 dark:text-gray-400">Status</div>
							<div class="text-sm font-medium text-gray-900 dark:text-gray-100">{{ detail.status || "—" }}</div>
						</div>
						<div>
							<div class="text-xs text-gray-500 dark:text-gray-400">Last 3 months</div>
							<div class="text-sm font-medium text-gray-900 dark:text-gray-100">{{ formatHours(detail.stats?.total_time_last_3_months) }}</div>
						</div>
						<div>
							<div class="text-xs text-gray-500 dark:text-gray-400">Open SO hours</div>
							<div class="text-sm font-medium">{{ detail.financial?.sales_order_total_hrs ?? "—" }}</div>
						</div>
						<div>
							<div class="text-xs text-gray-500 dark:text-gray-400">Delivered hours</div>
							<div class="text-sm font-medium">{{ formatHours(detail.financial?.delivered_total_hrs) }}</div>
						</div>
						<div>
							<div class="text-xs text-gray-500 dark:text-gray-400">Billable TS (not on DN)</div>
							<div class="text-sm font-medium">{{ formatHours(detail.financial?.total_hrs_timesheet) }}</div>
						</div>
						<div>
							<div class="text-xs text-gray-500 dark:text-gray-400">Remaining SO hours</div>
							<div class="text-sm font-medium">{{ formatHours(detail.financial?.remaining_hrs) }}</div>
						</div>
					</div>

					<div v-if="detail.previous_status" class="mt-4 rounded-lg bg-gray-50 p-4 text-sm dark:bg-gray-950">
						<div class="mb-2 text-xs font-medium uppercase tracking-wide text-gray-500">
							Previous review ({{ detail.previous_status.date }})
						</div>
						<div class="grid gap-2">
							<div><span class="text-gray-500">Maturity:</span> {{ shortLabel(detail.previous_status.maturity_level) }}</div>
							<div><span class="text-gray-500">Forecast:</span> {{ shortLabel(detail.previous_status.forecast) }}</div>
							<div><span class="text-gray-500">Trend:</span> {{ detail.previous_status.trend || "—" }}</div>
							<div><span class="text-gray-500">Statement:</span> {{ detail.previous_status.status_statement || "—" }}</div>
						</div>
					</div>
				</div>

				<div class="rounded-xl border border-gray-200 bg-white p-5 dark:border-gray-800 dark:bg-gray-900">
					<h3 class="mb-4 text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Meeting to-dos</h3>
					<ImplementationTodoList :todos="todos" @closed="onTodoClosed" />
					<div class="mt-4 border-t border-gray-100 pt-4 dark:border-gray-800">
						<ImplementationTodoQuickAdd
							:implementation="detail.name"
							:users="detail.users || []"
							:default-assignee="detail.account_manager"
							@created="onTodoCreated"
						/>
					</div>
				</div>
			</section>
		</div>
	</div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { call, toast } from "frappe-ui"
import ImplementationReviewForm from "../components/weeklyMonitoring/ImplementationReviewForm.vue"
import PredictionMonthEditor from "../components/weeklyMonitoring/PredictionMonthEditor.vue"
import ImplementationTodoList from "../components/weeklyMonitoring/ImplementationTodoList.vue"
import ImplementationTodoQuickAdd from "../components/weeklyMonitoring/ImplementationTodoQuickAdd.vue"

const API = "phamos.api.project_management_spa"

const route = useRoute()
const router = useRouter()

const loading = ref(true)
const saving = ref(false)
const error = ref("")
const detail = ref(null)
const flatQueue = ref([])

const formValues = ref({
	maturity_level: "",
	forecast: "",
	trend: "",
	status_statement: "",
})
const predictions = ref([])
const todos = ref([])

const queuePositionLabel = computed(() => {
	if (!flatQueue.value.length || !detail.value?.name) return ""
	const index = flatQueue.value.findIndex((row) => row.name === detail.value.name)
	if (index < 0) return ""
	return `${index + 1} of ${flatQueue.value.length}`
})

function formatHours(value) {
	if (value === null || value === undefined || value === "") return "—"
	return `${Number(value).toFixed(1)} h`
}

function shortLabel(value) {
	if (!value) return "—"
	const text = String(value)
	return text.length > 48 ? `${text.slice(0, 48)}…` : text
}

function applyDetail(data) {
	detail.value = data
	formValues.value = { ...(data.values || {}) }
	predictions.value = (data.predictions || []).map((row) => ({ ...row }))
	todos.value = [...(data.todos || [])]
}

function onTodoCreated(todo) {
	todos.value = [...todos.value, todo]
}

function onTodoClosed(name) {
	todos.value = todos.value.filter((todo) => todo.name !== name)
}

function findNextPendingName(currentName) {
	const rows = flatQueue.value
	const pending = rows.filter((row) => !row.reviewed_today)
	if (!currentName) return pending[0]?.name || null

	const index = rows.findIndex((row) => row.name === currentName)
	const after = rows.slice(index + 1).find((row) => !row.reviewed_today)
	if (after) return after.name

	return pending.find((row) => row.name !== currentName)?.name || null
}

async function navigateToDetail(name) {
	try {
		await router.push({ name: "WeeklyMonitoringDetail", params: { name } })
	} catch (e) {
		toast.error("Could not navigate to next implementation")
		throw e
	}
}

async function loadQueue() {
	try {
		const data = await call(`${API}.get_weekly_monitoring_queue`)
		flatQueue.value = (data.groups || []).flatMap((group) => group.items || [])
	} catch (e) {
		flatQueue.value = []
	}
}

async function loadDetail(name) {
	loading.value = true
	error.value = ""
	try {
		const data = await call(`${API}.get_weekly_monitoring_detail`, { name })
		applyDetail(data)
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not load implementation"
		detail.value = null
	} finally {
		loading.value = false
	}
}

async function save(andNext) {
	if (!detail.value?.name) return
	saving.value = true
	try {
		const updated = await call(`${API}.save_weekly_monitoring`, {
			name: detail.value.name,
			maturity_level: formValues.value.maturity_level,
			forecast: formValues.value.forecast,
			trend: formValues.value.trend,
			status_statement: formValues.value.status_statement,
			predictions: predictions.value,
		})
		toast.success("Implementation updated")
		if (andNext) {
			if (updated.next_name) {
				await navigateToDetail(updated.next_name)
			} else {
				toast.success("All implementations reviewed for today")
				try {
					await router.push({ name: "WeeklyMonitoring" })
				} catch (e) {
					toast.error("Could not return to queue")
				}
			}
			return
		}
		applyDetail(updated)
		await loadQueue()
	} catch (e) {
		toast.error(e?.messages?.[0] || e?.message || "Could not save")
	} finally {
		saving.value = false
	}
}

async function skip() {
	if (!detail.value?.name) return
	const nextName = findNextPendingName(detail.value.name)
	if (nextName) {
		await navigateToDetail(nextName)
	} else {
		try {
			await router.push({ name: "WeeklyMonitoring" })
		} catch (e) {
			toast.error("Could not return to queue")
		}
	}
}

function backToQueue() {
	router.push({ name: "WeeklyMonitoring" })
}

watch(
	() => route.params.name,
	(name) => {
		if (name) loadDetail(name)
	}
)

onMounted(async () => {
	await loadQueue()
	if (route.params.name) await loadDetail(route.params.name)
})
</script>
