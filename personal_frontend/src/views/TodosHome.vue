<template>
	<div class="h-full min-h-0 overflow-y-auto bg-surface-gray-1 p-5">
		<div class="mx-auto flex max-w-7xl flex-col gap-5">
			<div class="flex flex-wrap items-center justify-between gap-3">
				<p class="text-sm text-ink-gray-6">{{ headline }}</p>
				<div class="flex items-center gap-2">
					<TabButtons v-model="period" :buttons="PERIOD_BUTTONS" />
					<Button variant="subtle" @click="router.push({ name: 'TodosPlan' })">{{ dayButton }}</Button>
					<Button variant="solid" @click="showStartFocus = true">
						<template #prefix><FeatherIcon name="target" class="h-4 w-4" /></template>
						Start focus
					</Button>
				</div>
			</div>

			<div v-if="error" class="rounded-lg border border-outline-gray-2 bg-surface-red-1 p-4 text-sm text-ink-red-4">
				{{ error }}
			</div>
			<div v-else-if="loading && !data" class="flex min-h-64 items-center justify-center text-sm text-ink-gray-5">
				Loading your ToDos…
			</div>
			<template v-else-if="data">
				<section class="grid grid-cols-2 gap-3 xl:grid-cols-4">
					<StatCard
						label="Open now"
						:value="current.open"
						:hint="data.stale_count ? `${data.stale_count} need a decision` : 'Nothing stale'"
						:lines="[`${compare('open', 'level')} vs ${periodLabel} ago`]"
					/>
					<StatCard
						label="Closed"
						:value="current.closed"
						:hint="`in the last ${periodLabel}`"
						:lines="[`${compare('closed')} vs the ${periodLabel} before`]"
					/>
					<StatCard
						label="Dropped"
						:value="current.dropped"
						hint="decided not to do"
						:lines="[`${compare('dropped')} vs the ${periodLabel} before`]"
					/>
					<StatCard
						label="Closed vs open"
						:value="current.closed_share == null ? '—' : `${current.closed_share}% closed`"
						:hint="`${current.closed} closed · ${current.open} still open`"
						:lines="[`${compare('closed_share', 'percent')} vs the ${periodLabel} before`]"
					/>
				</section>

				<section class="grid grid-cols-1 gap-5 xl:grid-cols-2" aria-label="Targets">
					<ChallengeCard
						v-for="challenge in challenges.active"
						:key="challenge.name"
						:challenge="challenge"
						@end="endChallenge"
					/>
					<ChallengeCard v-if="!challenges.active.length && recentFinished" :challenge="recentFinished" />
					<div
						v-if="challenges.active.length < 2"
						class="flex flex-col items-start justify-center gap-2 rounded-lg border border-dashed border-outline-gray-3 p-5"
					>
						<p class="text-sm text-ink-gray-7">
							{{ challenges.active.length ? "Add a second target for important ToDos?" : "Want a target? Something like “close 2 a day for 10 days”." }}
						</p>
						<p class="text-xs text-ink-gray-5">Optional and private. Your own history suggests the number.</p>
						<Button size="sm" @click="showCreateChallenge = true">Set a target</Button>
					</div>
				</section>

				<section class="grid grid-cols-1 gap-5 xl:grid-cols-3">
					<div class="xl:col-span-2">
						<PeriodBars
							title="Created vs closed"
							:subtitle="leadTimeText"
							:periods="flowPeriods"
							:series="[{ label: 'Created' }, { label: 'Closed' }, { label: 'Dropped' }]"
							note="Number under a bar: how the backlog changed"
						/>
					</div>
					<section class="rounded-lg border border-outline-gray-2 bg-surface-white p-5">
						<h2 class="text-base font-semibold text-ink-gray-9">Done today</h2>
						<p class="mb-3 text-sm text-ink-gray-5">{{ doneTodayText }}</p>
						<ul v-if="data.today.done.length" class="space-y-2">
							<li v-for="todo in data.today.done" :key="todo.name" class="flex items-start gap-2 text-sm">
								<FeatherIcon name="check" class="mt-0.5 h-4 w-4 flex-none text-ink-green-3" />
								<button
									type="button"
									class="min-w-0 flex-1 truncate text-left text-ink-gray-8 hover:underline"
									@click="openTodo(todo.name)"
								>
									{{ todo.summary || todo.name }}
								</button>
								<FeatherIcon v-if="todo.important" name="star" class="mt-0.5 h-3.5 w-3.5 flex-none text-ink-amber-3" />
								<span v-if="todo.quick_win" class="flex-none text-xs text-ink-gray-5">quick win</span>
							</li>
						</ul>
						<p v-else class="text-sm text-ink-gray-5">Nothing closed yet today.</p>
					</section>
				</section>

				<section class="grid grid-cols-1 gap-5 xl:grid-cols-2">
					<section class="rounded-lg border border-outline-gray-2 bg-surface-white p-5">
						<div class="mb-3 flex items-start justify-between gap-3">
							<div>
								<h2 class="text-base font-semibold text-ink-gray-9">Oldest open</h2>
								<p class="text-sm text-ink-gray-5">Do it, give it a day, or drop it.</p>
							</div>
							<Button v-if="data.stale.length > 1" size="sm" @click="decide(data.stale)">
								Decide all stale ({{ data.stale.length }})
							</Button>
						</div>
						<ul v-if="data.oldest.length" class="divide-y divide-outline-gray-1">
							<li v-for="todo in data.oldest" :key="todo.name" class="flex items-center gap-3 py-2">
								<div class="min-w-0 flex-1">
									<button
										type="button"
										class="block w-full truncate text-left text-sm text-ink-gray-9 hover:underline"
										@click="openTodo(todo.name)"
									>
										{{ todo.summary || todo.name }}
									</button>
									<div class="mt-0.5 flex flex-wrap gap-x-3 text-xs text-ink-gray-5">
										<span>{{ ageLabel(todo.age_days) }} old</span>
										<span v-if="todo.overdue" class="text-ink-red-3">overdue</span>
										<span
											v-if="todo.reschedule_count"
											:class="todo.reschedule_count >= 3 ? 'text-ink-red-3' : ''"
											:title="`Postponed ${todo.reschedule_count} times`"
										>
											↻ {{ todo.reschedule_count }}
										</span>
									</div>
								</div>
								<Button size="sm" @click="decide([todo])">Decide</Button>
							</li>
						</ul>
						<p v-else class="text-sm text-ink-gray-5">No open ToDos. Well done.</p>
					</section>

					<div class="grid grid-cols-1 gap-5">
						<HorizontalBars title="Age of open ToDos" :rows="data.aging" />
						<HorizontalBars title="Closed in this period" :rows="closureRows" />
					</div>
				</section>
			</template>
		</div>

		<DecideTodoDialog v-model="showDecide" :todos="decideQueue" @decided="scheduleReload" />
		<StartFocusDialog v-model="showStartFocus" :preselect="focusPreselect" />
		<CreateChallengeDialog v-model="showCreateChallenge" @created="loadChallenges" />
	</div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue"
import { useRouter } from "vue-router"
import { call, TabButtons } from "frappe-ui"
import DecideTodoDialog from "@spa/components/DecideTodoDialog.vue"
import StartFocusDialog from "@/components/StartFocusDialog.vue"
import ChallengeCard from "@/components/ChallengeCard.vue"
import CreateChallengeDialog from "@/components/CreateChallengeDialog.vue"
import HorizontalBars from "@spa/components/dashboard/HorizontalBars.vue"
import PeriodBars from "@spa/components/dashboard/PeriodBars.vue"
import StatCard from "@spa/components/dashboard/StatCard.vue"
import { useUserRealtime } from "@spa/composables/useUserRealtime.js"
import { ageLabel, formatComparison, formatDays, netLabel, pluralize } from "@spa/utils/dashboardFormat.js"
import spaConfig from "@/config"

const API = spaConfig.api
const PERIOD_KEY = "personal-todos-dashboard-period"
const PERIOD_BUTTONS = [
	{ label: "7 days", value: "7" },
	{ label: "30 days", value: "30" },
	{ label: "90 days", value: "90" },
]

const router = useRouter()
const data = ref(null)
const loading = ref(false)
const error = ref("")
const period = ref(readPeriod())
const showDecide = ref(false)
const decideQueue = ref([])
const showStartFocus = ref(false)
const showCreateChallenge = ref(false)
const dayState = ref(null)
// The one next step for the day: plan it, follow it, or see it closed (#1559).
const dayButton = computed(() => {
	const state = dayState.value
	if (!state || state.status === "None" || (state.status === "Draft" && !state.planned)) return "Plan my day"
	if (state.status === "Closed") return "Day done"
	return `My day: ${state.done} of ${state.planned} done`
})
const challenges = ref({ active: [], recent: [] })
// A challenge that finished in the last week stays visible until a new one starts.
const recentFinished = computed(() => {
	const last = challenges.value.recent?.[0]
	if (!last?.ended_on) return null
	const days = (Date.now() - new Date(String(last.ended_on)).getTime()) / 86400000
	return days <= 7 ? last : null
})
// Suggest the oldest stale ToDos first: focus is the strongest way to finally close them.
const focusPreselect = computed(() => (data.value?.stale || []).slice(0, 3).map((todo) => todo.name))

const current = computed(() => data.value?.windows?.current || {})
const previous = computed(() => data.value?.windows?.previous || {})
const periodLabel = computed(() => `${period.value} days`)

const headline = computed(() => {
	if (!data.value) return "Your ToDos at a glance."
	const done = data.value.today.done.length
	const stale = data.value.stale_count
	if (!current.value.open) return "No open ToDos."
	const parts = [`${done} closed today`]
	if (stale) parts.push(`${pluralize(stale, "ToDo needs", "ToDos need")} a decision`)
	return parts.join(" · ")
})

const leadTimeText = computed(() => {
	const lead = data.value?.lead_time
	if (!lead?.sample) return "Lead times appear once you close ToDos."
	return `Half of your closed ToDos took ${formatDays(lead.p50_days)} or less, 85% took ${formatDays(lead.p85_days)} or less.`
})

const flowPeriods = computed(() =>
	(data.value?.flow || []).map((bar) => ({
		label: bar.label,
		values: [bar.created, bar.closed, bar.dropped],
		footer: netLabel(bar.net),
		footerTone: bar.net > 0 ? "bad" : bar.net < 0 ? "good" : "",
	}))
)

const closureRows = computed(() => {
	const c = data.value?.closures || {}
	const rows = [
		{ label: "Important", value: c.important || 0, theme: "amber" },
		{ label: "Other", value: c.other || 0, theme: "blue" },
		{ label: "…of these, quick wins (under 15 min)", value: c.quick_wins || 0, theme: "gray" },
		{ label: "Dropped", value: c.dropped || 0, theme: "red" },
	]
	if (c.by_others) rows.push({ label: "Closed or removed by others", value: c.by_others, theme: "gray" })
	return rows
})

const doneTodayText = computed(() => {
	const done = data.value?.today.done || []
	if (!done.length) return data.value?.today.dropped ? `${data.value.today.dropped} dropped so far.` : "A first one sets the tone."
	const important = done.filter((t) => t.important).length
	return important ? `${done.length} done, ${important} of them important.` : `${done.length} done.`
})

function compare(key, kind = "number") {
	return formatComparison(current.value[key], previous.value[key], kind)
}

function readPeriod() {
	try {
		const saved = localStorage.getItem(PERIOD_KEY)
		return ["7", "30", "90"].includes(saved) ? saved : "30"
	} catch (e) {
		return "30"
	}
}

async function load() {
	loading.value = true
	error.value = ""
	try {
		data.value = await call(`${API}.get_todo_dashboard`, { period: Number(period.value) })
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not load the ToDo dashboard"
	} finally {
		loading.value = false
	}
}

let reloadTimer = null
async function loadDayState() {
	try {
		dayState.value = await call(`${API}.get_day_state`)
	} catch {
		dayState.value = null
	}
}

async function loadChallenges() {
	try {
		challenges.value = await call(`${API}.get_challenges`)
	} catch {
		challenges.value = { active: [], recent: [] }
	}
}

async function endChallenge(challenge) {
	if (!window.confirm(`End “${challenge.title}” now? The days so far stay counted.`)) return
	try {
		await call(`${API}.end_challenge`, { name: challenge.name })
	} finally {
		loadChallenges()
	}
}

function scheduleReload() {
	clearTimeout(reloadTimer)
	reloadTimer = setTimeout(load, 300)
}

function decide(todos) {
	decideQueue.value = todos
	showDecide.value = true
}

function openTodo(name) {
	router.push({ name: "TodoDetail", params: { name } })
}

watch(period, (value) => {
	try {
		localStorage.setItem(PERIOD_KEY, value)
	} catch (e) {
		/* ignore */
	}
	load()
})

useUserRealtime("cockpit_todos_changed", () => {
	load()
	loadChallenges()
	loadDayState()
})
onMounted(() => {
	load()
	loadChallenges()
	loadDayState()
})
</script>
