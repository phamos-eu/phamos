<template>
	<!-- The planner of one day (#1559); the My Day timeline (#1573) shows it for today and on demand
	     for future days. -->
	<div>
		<div class="flex flex-col gap-5">
			<div v-if="error" class="rounded-lg border border-outline-gray-2 bg-surface-red-1 p-4 text-sm text-ink-red-4">
				{{ error }}
			</div>
			<div v-else-if="!plan" class="flex min-h-64 items-center justify-center text-sm text-ink-gray-5">
				{{ __("Loading your day…") }}
			</div>

			<template v-else>
				<!-- Header: day, capacity, the one next step -->
				<section class="rounded-lg border border-outline-gray-2 bg-surface-white p-5">
					<div class="flex flex-wrap items-start justify-between gap-4">
						<div>
							<h2 class="text-lg font-semibold text-ink-gray-9">{{ dayTitle }}</h2>
							<p class="text-sm text-ink-gray-6">{{ statusLine }}</p>
						</div>
						<div class="flex gap-2">
							<Button
								v-if="plan.status === 'Draft' && isToday"
								variant="solid"
								:disabled="!activeItems.length"
								:loading="busy === 'start'"
								@click="startDay"
							>
								{{ __("Start the day") }}
							</Button>
							<Button v-if="plan.status === 'Confirmed'" variant="solid" @click="showShutdown = true">{{ __("Shut down") }}</Button>
						</div>
					</div>

					<div v-if="plan.status !== 'Closed'" class="mt-4">
						<div class="mb-1 flex justify-between text-xs text-ink-gray-6">
							<span>{{ capacityText }}</span>
							<span :class="overCap ? 'text-ink-amber-4' : ''">{{ __("{0} of at most {1} ToDos", [openItems.length, plan.cap]) }}</span>
						</div>
						<div class="h-2 overflow-hidden rounded-full" style="background: var(--surface-gray-3)" role="meter"
							:aria-valuenow="plan.remaining_minutes" aria-valuemin="0" :aria-valuemax="plan.capacity_minutes"
							:aria-label="capacityText">
							<div class="h-full rounded-full transition-all" :style="capacityStyle" />
						</div>
						<p v-if="overCapacity || overCap" class="mt-1 text-xs text-ink-amber-4">
							{{ __("More than fits. Move something to another day or drop it: a short plan you finish beats a long one you carry.") }}
						</p>
						<p v-if="calibrationText" class="mt-1 text-xs text-ink-gray-5">{{ calibrationText }}</p>
					</div>

					<ol v-if="plan.status === 'Draft' && isToday" class="mt-4 flex flex-wrap gap-x-5 gap-y-1 text-xs text-ink-gray-5">
						<li v-for="(step, index) in RITUAL" :key="step"><span class="font-medium text-ink-gray-7">{{ index + 1 }}.</span> {{ __(step) }}</li>
					</ol>
				</section>

				<!-- Done for the day -->
				<section v-if="plan.status === 'Closed'" class="rounded-lg border border-outline-gray-2 bg-surface-white p-5">
					<h2 class="text-lg font-semibold text-ink-gray-9">{{ __("Done for the day.") }}</h2>
					<p class="mt-1 text-sm text-ink-gray-6">{{ closedSummary }}</p>
					<p v-if="plan.reflection" class="mt-3 text-sm italic text-ink-gray-7">“{{ plan.reflection }}”</p>
					<p class="mt-3 text-sm text-ink-gray-6">{{ __("Everything open has a next step. You can let work go now.") }}</p>
					<Button class="mt-4" @click="openDate(plan.next_working_day)">{{ __("Look at {0}", [formatDate(plan.next_working_day)]) }}</Button>
				</section>

				<div class="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
					<!-- The plan -->
					<section class="min-w-0 rounded-lg border border-outline-gray-2 bg-surface-white p-5">
						<h3 class="mb-3 text-base font-semibold text-ink-gray-9">{{ isToday ? __("Today") : formatDate(plan.date) }}</h3>
						<p v-if="!plan.items.length" class="text-sm text-ink-gray-5">
							{{ __("Nothing planned yet. Pick a few from the right, the ones that would make this day a good one.") }}
						</p>
						<ul class="space-y-1.5">
							<li
								v-for="(item, index) in plan.items"
								:key="item.todo"
								class="flex items-start gap-2 rounded-md border border-outline-gray-1 px-2.5 py-2 text-sm"
								:class="item.outcome === 'Open' ? 'bg-surface-gray-1' : 'bg-surface-white opacity-70'"
							>
								<input
									type="checkbox"
									class="mt-0.5 h-4 w-4 flex-none rounded border-outline-gray-3"
									:checked="item.outcome === 'Done'"
									:disabled="item.outcome !== 'Open' || busy === item.todo"
									:aria-label="__('Mark {0} as done', [item.summary])"
									@change="close(item)"
								/>
								<div class="min-w-0 flex-1">
									<button
										type="button"
										class="block w-full truncate text-left hover:underline"
										:class="item.outcome === 'Done' ? 'text-ink-gray-5 line-through' : 'text-ink-gray-9'"
										@click="router.push({ name: 'TodoDetail', params: { name: item.todo } })"
									>
										{{ item.summary || item.todo }}
									</button>
									<div class="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-ink-gray-5">
										<span v-if="item.important" class="text-ink-amber-3">★</span>
										<span v-if="item.rollover_count" :class="item.rollover_count >= plan.rollover_decide ? 'text-ink-red-3' : ''"
											:title="__('Carried over {0} times', [item.rollover_count])">↻ {{ item.rollover_count }}</span>
										<span v-if="plan.fixed_at && item.outcome !== 'Moved'">{{ item.planned ? __("planned") : __("added later") }}</span>
										<span v-if="item.outcome === 'Moved'">{{ __("moved to {0}", [formatDate(item.moved_to)]) }}</span>
										<span v-if="item.outcome === 'Dropped'">{{ __("dropped") }}</span>
										<select
											v-if="item.outcome === 'Open' && plan.status !== 'Closed'"
											class="rounded border-none bg-transparent py-0 pl-0 pr-5 text-xs text-ink-gray-6 focus:ring-0"
											:value="item.estimate_minutes || ''"
											:aria-label="__('Estimate for {0}', [item.summary])"
											@change="setEstimate(item, $event.target.value)"
										>
											<option value="">{{ __("no estimate") }}</option>
											<option v-for="m in ESTIMATES" :key="m" :value="m">~{{ minutesLabel(m) }}</option>
										</select>
									</div>
								</div>
								<div v-if="plan.status !== 'Closed' && item.outcome === 'Open'" class="flex flex-none items-center">
									<Button variant="ghost" size="sm" :disabled="index === 0" :aria-label="__('Move {0} up', [item.summary])" @click="move(item, 'up')">
										<FeatherIcon name="chevron-up" class="h-4 w-4" />
									</Button>
									<Button variant="ghost" size="sm" :disabled="index === plan.items.length - 1" :aria-label="__('Move {0} down', [item.summary])" @click="move(item, 'down')">
										<FeatherIcon name="chevron-down" class="h-4 w-4" />
									</Button>
									<Button variant="ghost" size="sm" :aria-label="__('Remove {0} from the plan', [item.summary])" @click="remove(item)">
										<FeatherIcon name="x" class="h-4 w-4" />
									</Button>
								</div>
							</li>
						</ul>
					</section>

					<!-- Candidates -->
					<section v-if="plan.status !== 'Closed'" class="min-w-0 rounded-lg border border-outline-gray-2 bg-surface-white p-5">
						<h3 class="mb-3 text-base font-semibold text-ink-gray-9">{{ __("Worth considering") }}</h3>
						<p v-if="!visibleGroups.length" class="text-sm text-ink-gray-5">
							{{ __("Nothing overdue, due or flagged.") }}
							<button type="button" class="underline" @click="router.push({ name: 'TodosList' })">{{ __("Pick from the list if you like.") }}</button>
						</p>
						<div v-for="group in visibleGroups" :key="group.key" class="mb-4">
							<h4 class="mb-1 text-xs font-medium uppercase tracking-wide text-ink-gray-5">{{ __(group.label) }}</h4>
							<ul class="space-y-1">
								<li v-for="todo in group.items" :key="todo.name" class="flex items-center gap-2 text-sm">
									<span class="min-w-0 flex-1 truncate text-ink-gray-8">{{ todo.summary || todo.name }}</span>
									<span v-if="todo.rollover_count" class="flex-none text-xs"
										:class="todo.rollover_count >= plan.rollover_decide ? 'text-ink-red-3' : 'text-ink-gray-5'"
										:title="__('Not finished {0} times', [todo.rollover_count])">↻ {{ todo.rollover_count }}</span>
									<span v-if="todo.estimate_minutes" class="flex-none text-xs text-ink-gray-5">~{{ minutesLabel(todo.estimate_minutes) }}</span>
									<Button v-if="todo.rollover_count >= plan.rollover_decide" size="sm" @click="decide(todo)">{{ __("Decide") }}</Button>
									<Button size="sm" :loading="busy === todo.name" @click="add(todo)">{{ __("Add") }}</Button>
								</li>
							</ul>
						</div>
					</section>
				</div>
			</template>
		</div>

		<ShutdownDialog v-if="plan" v-model="showShutdown" :plan="plan" @done="apply" />
		<DecideTodoDialog v-model="showDecide" :todos="decideQueue" @decided="load" />
	</div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue"
import { useRouter } from "vue-router"
import { call } from "frappe-ui"
import { notify } from "@spa/utils/notify.js"
import DecideTodoDialog from "@spa/components/DecideTodoDialog.vue"
import { useUserRealtime } from "@spa/composables/useUserRealtime.js"
import { formatDate, weekdayName } from "@spa/utils/datetime.js"
import { __ } from "@spa/utils/i18n.js"
import spaConfig from "@/config"
import ShutdownDialog from "@/components/ShutdownDialog.vue"

const API = spaConfig.api
const ESTIMATES = [15, 30, 60, 90, 120, 180, 240]
const RITUAL = [
	"Look at what was left last time",
	"Pick a few, at most six",
	"Estimate them",
	"Check that they fit",
	"Start the day",
]

const router = useRouter()
const plan = ref(null)
const error = ref("")
const busy = ref("")
const showShutdown = ref(false)
const showDecide = ref(false)
const decideQueue = ref([])

const props = defineProps({
	// YYYY-MM-DD; empty means today.
	date: { type: String, default: "" },
})
const emit = defineEmits(["open-date", "changed"])
const date = computed(() => props.date || null)
const isToday = computed(() => plan.value && String(plan.value.date) === String(plan.value.today))
const activeItems = computed(() => (plan.value?.items || []).filter((i) => !["Moved", "Dropped"].includes(i.outcome)))
const openItems = computed(() => activeItems.value.filter((i) => i.outcome === "Open"))
const doneItems = computed(() => activeItems.value.filter((i) => i.outcome === "Done"))
const overCap = computed(() => openItems.value.length > (plan.value?.cap || 6))
const overCapacity = computed(() => plan.value && plan.value.remaining_minutes > plan.value.capacity_minutes)
const visibleGroups = computed(() => (plan.value?.candidates || []).filter((g) => g.items.length))

const dayTitle = computed(() => {
	if (!plan.value) return ""
	const weekday = weekdayName(plan.value.date, "long")
	return isToday.value
		? __("Today, {0} {1}", [weekday, formatDate(plan.value.date)])
		: `${weekday} ${formatDate(plan.value.date)}`
})
const statusLine = computed(() => {
	const p = plan.value
	if (!p) return ""
	if (p.status === "Closed") return __("Shut down.")
	if (p.status === "Confirmed") return __("{0} of {1} done. Shut down when you stop working.", [doneItems.value.length, activeItems.value.length])
	if (p.auto_fixed) return __("The plan was fixed at 10:00. Start the day whenever you are ready.")
	if (!isToday.value) return __("Plan ahead. You start the day on the day itself.")
	return __("Plan a few ToDos, then start the day.")
})
const capacityText = computed(() => {
	const p = plan.value
	const left = minutesLabel(p.remaining_minutes)
	const total = minutesLabel(p.capacity_minutes)
	if (!p.unestimated) return __("{0} of {1} for ToDos", [left, total])
	return p.unestimated === 1
		? __("{0} of {1} for ToDos (1 ToDo without estimate counted as {2} min)", [left, total, p.default_estimate_minutes])
		: __("{0} of {1} for ToDos ({2} ToDos without estimate counted as {3} min)", [left, total, p.unestimated, p.default_estimate_minutes])
})
const capacityStyle = computed(() => {
	const p = plan.value
	const share = Math.min(p.remaining_minutes / (p.capacity_minutes || 1), 1) * 100
	const colour = overCapacity.value ? "var(--ink-amber-3)" : "var(--ink-blue-3)"
	return `width: ${share}%; background: ${colour}`
})
const calibrationText = computed(() => {
	const factor = plan.value?.calibration?.factor
	if (!factor || Math.abs(factor - 1) < 0.15) return ""
	return factor > 1
		? __("In focus your ToDos took {0}× your estimate. Plan with some room.", [factor])
		: __("In focus your ToDos took {0}× your estimate. You may plan a little more.", [factor])
})
const closedSummary = computed(() => {
	const moved = plan.value.items.filter((i) => i.outcome === "Moved").length
	const dropped = plan.value.items.filter((i) => i.outcome === "Dropped").length
	const done = doneItems.value.length
	const parts = [done === 1 ? __("1 ToDo done") : __("{0} ToDos done", [done])]
	if (moved) parts.push(__("{0} moved", [moved]))
	if (dropped) parts.push(__("{0} dropped", [dropped]))
	return `${parts.join(", ")}.`
})

function minutesLabel(minutes) {
	const m = Math.round(minutes || 0)
	if (m < 60) return __("{0} min", [m])
	const h = Math.floor(m / 60)
	return m % 60 ? __("{0} h {1} min", [h, m % 60]) : __("{0} h", [h])
}

function errorText(e, fallback) {
	return e?.messages?.[0] || e?.message || fallback
}

function apply(result) {
	plan.value = result
	emit("changed", result)
}

async function load() {
	error.value = ""
	try {
		plan.value = await call(`${API}.get_day_plan`, { date: date.value })
	} catch (e) {
		error.value = errorText(e, __("Could not load your day"))
	}
}

async function run(key, method, args, message) {
	busy.value = key
	try {
		apply(await call(`${API}.${method}`, { ...args, date: date.value }))
		if (message) notify.success(message)
	} catch (e) {
		notify.error(errorText(e, __("That did not work")))
	} finally {
		busy.value = ""
	}
}

const add = (todo) => run(todo.name, "add_to_day", { todo: todo.name })
const remove = (item) => run(item.todo, "remove_from_day", { todo: item.todo })
const move = (item, direction) => run(item.todo, "move_in_day", { todo: item.todo, direction })
const startDay = () => run("start", "start_day", {}, __("Day started. Go for the first one."))

async function close(item) {
	busy.value = item.todo
	try {
		await call(`${API}.close_todo`, { name: item.todo })
		notify.success(__("Done. One less."))
		await load()
	} catch (e) {
		notify.error(errorText(e, __("Could not close the ToDo")))
	} finally {
		busy.value = ""
	}
}

async function setEstimate(item, value) {
	try {
		await call(`${API}.update_todo`, { name: item.todo, estimate_minutes: Number(value) || 0 })
		await load()
	} catch (e) {
		notify.error(errorText(e, __("Could not save the estimate")))
	}
}

function decide(todo) {
	decideQueue.value = [todo]
	showDecide.value = true
}

function openDate(value) {
	emit("open-date", String(value))
}

watch(date, load)
useUserRealtime("cockpit_todos_changed", () => {
	if (!busy.value && !showShutdown.value) load()
})
onMounted(load)
</script>
