<template>
	<div class="h-full w-full overflow-y-auto px-6 py-6">
		<div class="mb-6 flex flex-wrap items-start justify-between gap-4">
			<div>
				<h2 class="text-lg font-semibold text-gray-900 dark:text-gray-100">Weekly Implementation Monitoring</h2>
				<p class="mt-1 text-sm text-gray-500 dark:text-gray-400">
					{{ todayLabel }} · {{ reviewedCount }} / {{ totalCount }} reviewed today
				</p>
			</div>
			<div class="flex items-center gap-2">
				<input
					v-model="search"
					type="search"
					placeholder="Search implementations…"
					class="h-9 w-56 rounded-md border border-gray-300 bg-white px-3 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
				/>
				<Button variant="solid" :disabled="!firstPendingName" @click="startMeeting">
					Start meeting
				</Button>
			</div>
		</div>

		<div v-if="loading" class="text-sm text-gray-500 dark:text-gray-400">Loading queue…</div>
		<div v-else-if="error" class="text-sm text-red-600 dark:text-red-400">{{ error }}</div>

		<div
			v-else-if="!filteredGroups.length"
			class="rounded-lg border border-dashed border-gray-300 p-8 text-center text-sm text-gray-500 dark:border-gray-700 dark:text-gray-400"
		>
			No active implementations found.
		</div>

		<div v-else class="space-y-8">
			<section v-for="group in filteredGroups" :key="group.maturity_sort">
				<div class="mb-3 flex flex-wrap items-center justify-between gap-2 border-b border-gray-200 pb-2 dark:border-gray-800">
					<h3 class="text-base font-semibold text-gray-900 dark:text-gray-100">
						{{ group.maturity_group_title }}
					</h3>
					<span class="text-sm text-gray-500 dark:text-gray-400">
						{{ group.reviewed_count }} / {{ group.total_count }} reviewed today
					</span>
				</div>

				<div class="overflow-hidden rounded-xl border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900">
					<table class="min-w-full divide-y divide-gray-200 dark:divide-gray-800">
						<thead class="bg-gray-50 dark:bg-gray-950">
							<tr>
								<th class="w-10 px-3 py-3"></th>
								<th class="px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-gray-500">Implementation</th>
								<th class="px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-gray-500">Customer</th>
								<th class="px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-gray-500">Account Manager</th>
								<th class="px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-gray-500">Forecast</th>
								<th class="px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-gray-500">Trend</th>
								<th class="px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-gray-500">Status</th>
							</tr>
						</thead>
						<tbody class="divide-y divide-gray-100 dark:divide-gray-800">
							<template v-for="row in group.items" :key="row.name">
								<tr
									class="cursor-pointer transition hover:bg-gray-50 dark:hover:bg-gray-800/60"
									@click="openDetail(row.name)"
								>
									<td class="px-3 py-3" @click.stop>
										<button
											type="button"
											class="rounded p-1 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800"
											@click="toggleExpanded(row.name)"
										>
											<FeatherIcon
												:name="expanded[row.name] ? 'chevron-down' : 'chevron-right'"
												class="h-4 w-4"
											/>
										</button>
									</td>
									<td class="px-4 py-3">
										<div class="font-medium text-gray-900 dark:text-gray-100">{{ row.name }}</div>
										<div class="mt-1 flex items-center gap-2">
											<span
												class="inline-flex rounded-full px-2 py-0.5 text-[11px] font-medium"
												:class="row.reviewed_today ? 'bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300' : 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300'"
											>
												{{ row.reviewed_today ? "Reviewed today" : "Pending" }}
											</span>
											<span v-if="row.todos?.length" class="text-[11px] text-gray-400">
												{{ row.todos.length }} to-do{{ row.todos.length === 1 ? "" : "s" }}
											</span>
											<a
												:href="row.desk_url"
												class="text-[11px] text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
												@click.stop
											>
												Desk
											</a>
										</div>
									</td>
									<td class="px-4 py-3 text-sm text-gray-600 dark:text-gray-300">{{ row.customer || "—" }}</td>
									<td class="px-4 py-3 text-sm text-gray-600 dark:text-gray-300">{{ row.owner_name || "—" }}</td>
									<td class="px-4 py-3 text-xs text-gray-600 dark:text-gray-300">{{ shortLabel(row.forecast) }}</td>
									<td class="px-4 py-3 text-sm text-gray-600 dark:text-gray-300">{{ row.trend || "—" }}</td>
									<td class="px-4 py-3 text-sm text-gray-600 dark:text-gray-300">{{ row.status || "—" }}</td>
								</tr>
								<tr v-if="expanded[row.name]" :key="`${row.name}-todos`">
									<td colspan="7" class="bg-gray-50 px-4 py-4 dark:bg-gray-950">
										<div class="space-y-4">
											<ImplementationTodoList
												:todos="row.todos || []"
												compact
												@closed="(name) => onTodoClosed(row, name)"
											/>
											<ImplementationTodoQuickAdd
												:implementation="row.name"
												:users="users"
												:default-assignee="row.account_manager"
												@created="(todo) => onTodoCreated(row, todo)"
											/>
										</div>
									</td>
								</tr>
							</template>
						</tbody>
					</table>
				</div>
			</section>
		</div>
	</div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue"
import { useRouter } from "vue-router"
import { call } from "frappe-ui"
import ImplementationTodoList from "../components/weeklyMonitoring/ImplementationTodoList.vue"
import ImplementationTodoQuickAdd from "../components/weeklyMonitoring/ImplementationTodoQuickAdd.vue"

const API = "phamos.api.project_management_spa"

const router = useRouter()
const loading = ref(true)
const error = ref("")
const search = ref("")
const groups = ref([])
const totalCount = ref(0)
const reviewedCount = ref(0)
const users = ref([])
const expanded = reactive({})

const todayLabel = new Date().toLocaleDateString(undefined, {
	weekday: "long",
	year: "numeric",
	month: "long",
	day: "numeric",
})

const flatRows = computed(() => groups.value.flatMap((group) => group.items || []))

const filteredGroups = computed(() => {
	const q = search.value.trim().toLowerCase()
	if (!q) return groups.value

	return groups.value
		.map((group) => ({
			...group,
			items: (group.items || []).filter((row) =>
				[row.name, row.customer, row.owner_name, row.status, row.trend, row.forecast, row.maturity_level]
					.filter(Boolean)
					.some((v) => String(v).toLowerCase().includes(q))
			),
		}))
		.filter((group) => group.items.length)
		.map((group) => ({
			...group,
			reviewed_count: group.items.filter((row) => row.reviewed_today).length,
			total_count: group.items.length,
		}))
})

const firstPendingName = computed(() => flatRows.value.find((row) => !row.reviewed_today)?.name || null)

function shortLabel(value) {
	if (!value) return "—"
	const text = String(value)
	return text.length > 28 ? `${text.slice(0, 28)}…` : text
}

function toggleExpanded(name) {
	expanded[name] = !expanded[name]
}

function openDetail(name) {
	router.push({ name: "WeeklyMonitoringDetail", params: { name } })
}

function startMeeting() {
	if (firstPendingName.value) openDetail(firstPendingName.value)
}

function onTodoCreated(row, todo) {
	if (!row.todos) row.todos = []
	row.todos.push(todo)
}

function onTodoClosed(row, name) {
	if (!row.todos) return
	row.todos = row.todos.filter((todo) => todo.name !== name)
}

async function loadUsers() {
	try {
		users.value = await call(`${API}.get_weekly_monitoring_todo_users`)
	} catch (e) {
		users.value = []
	}
}

onMounted(async () => {
	try {
		const [queueData] = await Promise.all([
			call(`${API}.get_weekly_monitoring_queue`),
			loadUsers(),
		])
		groups.value = queueData.groups || []
		totalCount.value = queueData.total_count || 0
		reviewedCount.value = queueData.reviewed_today_count || 0
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not load weekly monitoring queue"
	} finally {
		loading.value = false
	}
})
</script>
