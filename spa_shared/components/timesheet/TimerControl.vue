<template>
	<div v-if="state?.available" class="flex items-center gap-1">
		<!-- Idle -->
		<template v-if="!session">
			<Button
				v-if="startButton"
				size="sm"
				variant="ghost"
				:disabled="!state.can_start"
				:title="blockTitle"
				@click="showStart = true"
			>
				<template #prefix><FeatherIcon name="play" class="h-4 w-4" /></template>
				{{ __("Start timer") }}
			</Button>
			<Button
				v-if="state.blocking_drafts?.length"
				size="sm"
				variant="ghost"
				:title="__('Discard the empty draft {0}', [state.blocking_drafts[0].name])"
				:loading="busy === 'discard'"
				@click="discard(state.blocking_drafts[0])"
			>
				{{ __("Discard draft") }}
			</Button>
		</template>

		<!-- Waiting for the time-limit decision -->
		<Button v-else-if="session.state === 'limit_exceeded'" size="sm" variant="subtle" theme="orange" @click="showLimit = true">
			<template #prefix><FeatherIcon name="alert-triangle" class="h-4 w-4" /></template>
			{{ __("Time limit") }}
		</Button>

		<!-- Running or paused -->
		<template v-else>
			<Popover placement="bottom-end">
				<template #target="{ togglePopover }">
					<button
						type="button"
						class="flex h-7 items-center gap-2 rounded px-2 text-sm hover:bg-surface-gray-2"
						:aria-label="clockLabel"
						@click="togglePopover"
					>
						<span class="font-mono tabular-nums" :class="clockClass" role="timer">{{ clock }}</span>
						<span class="hidden max-w-[12rem] truncate text-ink-gray-7 md:inline">{{ session.project_name }}</span>
					</button>
				</template>
				<template #body-main>
					<div class="w-72 space-y-2 p-3 text-sm">
						<div class="font-medium text-ink-gray-9">{{ session.project_name }}</div>
						<div class="text-ink-gray-7">{{ session.goal }}</div>
						<div v-if="session.task_subject" class="text-xs text-ink-gray-5">{{ __("Task: {0}", [session.task_subject]) }}</div>
						<div v-if="session.gitlab_issue_title" class="text-xs text-ink-gray-5">{{ __("Issue: {0}", [session.gitlab_issue_title]) }}</div>
						<div class="flex justify-between text-xs text-ink-gray-6">
							<span>{{ __("Started {0} · {1} worked", [formatTime(session.from_time), formatMinutes(elapsed)]) }}</span>
							<span :class="over ? 'text-ink-red-4' : ''">{{ budget }}</span>
						</div>
						<div v-if="session.state === 'paused'" class="text-xs text-ink-amber-4">
							{{ __("Break: {0}, {1} so far", [session.break_goal || __("break"), breakText]) }}
						</div>
						<button type="button" class="text-xs text-ink-gray-5 hover:underline" @click="openDesk(session.desk_url)">
							{{ __("Open the record in Desk") }} ↗
						</button>
					</div>
				</template>
			</Popover>
			<!-- Plain buttons: frappe-ui's Button drops aria-label on icon-only buttons. -->
			<button
				v-if="session.state === 'running'"
				type="button"
				class="flex h-7 w-7 items-center justify-center rounded text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-9 disabled:opacity-50"
				:aria-label="__('Pause the timer')"
				:title="__('Pause')"
				@click="showPause = true"
			>
				<FeatherIcon name="pause" class="h-4 w-4" />
			</button>
			<button v-else type="button" class="flex h-7 w-7 items-center justify-center rounded text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-9 disabled:opacity-50" :aria-label="__('Resume the timer')" :title="__('Resume')" @click="showBreak = true">
				<FeatherIcon name="play" class="h-4 w-4" />
			</button>
			<button type="button" class="flex h-7 w-7 items-center justify-center rounded text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-9 disabled:opacity-50" :aria-label="__('Stop the timer')" :title="__('Stop')" @click="showStop = true">
				<FeatherIcon name="square" class="h-4 w-4" />
			</button>
		</template>

		<StartTimerDialog v-model="showStart" @started="onStarted" />
		<StopTimerDialog
			v-model="showStop"
			:session="session"
			:default-activity-type="state.default_activity_type || ''"
			@stopped="onStopped"
			@limit="onLimit"
		/>
		<PauseDialog v-model="showPause" :session="session" @paused="setTimer" />
		<BreakDialog v-model="showBreak" :session="session" :break-seconds="breakSeconds" @resumed="onResumed" />
		<TimeLimitDialog v-model="showLimit" :session="session" @done="onLimitDone" />
	</div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { call, Popover } from "frappe-ui"
import { openDesk } from "@spa/utils/appWindow.js"
import { formatTime as formatTimeFull } from "@spa/utils/datetime.js"
import { __ } from "@spa/utils/i18n.js"
import { notify } from "@spa/utils/notify.js"
import { budgetText, countdown, formatMinutes, isOverBudget, liveBreak, liveElapsed } from "@spa/utils/timerClock.js"
import { setTimer, timer, loadTimer } from "@spa/timerStore.js"
import spaConfig from "@/config"
import BreakDialog from "./BreakDialog.vue"
import PauseDialog from "./PauseDialog.vue"
import StartTimerDialog from "./StartTimerDialog.vue"
import StopTimerDialog from "./StopTimerDialog.vue"
import TimeLimitDialog from "./TimeLimitDialog.vue"

defineProps({
	// Show "Start timer" while idle. Off when the cockpit starts timers from a Create menu
	// (requestTimerStart); running, paused and blocked states are always shown.
	startButton: { type: Boolean, default: true },
})

const API = spaConfig.api
const tick = ref(Date.now())
const busy = ref("")
const showStart = ref(false)
const showStop = ref(false)
const showBreak = ref(false)
const showPause = ref(false)
const showLimit = ref(false)
let ticker = null

const formatTime = (value) => formatTimeFull(value).slice(0, 5)
const state = computed(() => timer.state)
const session = computed(() => state.value?.session || null)
const sinceLoad = computed(() => (tick.value - timer.loadedAt) / 1000)
const elapsed = computed(() => liveElapsed(session.value, sinceLoad.value))
// Counts down from the target: the session's expected time, or the break's estimate while paused.
const clockState = computed(() =>
	session.value?.state === "paused"
		? countdown(session.value.break_expected, breakSeconds.value)
		: countdown(session.value?.expected_time, elapsed.value)
)
const clock = computed(() => clockState.value.text)
const clockClass = computed(() => {
	if (clockState.value.over) return "text-ink-red-4"
	return session.value?.state === "running" ? "text-ink-green-3" : "text-ink-amber-3"
})
const clockLabel = computed(() => {
	const project = session.value?.project_name || ""
	const running = session.value?.state === "running"
	if (clockState.value.over) {
		const by = clock.value.slice(1)
		return running ? __("Timer running, over by {0}, {1}", [by, project]) : __("Break running, over by {0}, {1}", [by, project])
	}
	return running ? __("Timer running, {0} left, {1}", [clock.value, project]) : __("Break running, {0} left, {1}", [clock.value, project])
})
const budget = computed(() => budgetText(session.value, elapsed.value))
const over = computed(() => isOverBudget(session.value, elapsed.value))
const breakSeconds = computed(() => liveBreak(session.value, state.value?.server_now, sinceLoad.value))
const breakText = computed(() => formatMinutes(breakSeconds.value))
const blockTitle = computed(() => {
	const draft = state.value?.blocking_drafts?.[0]
	return draft ? __("Finish or discard the empty draft {0} first", [draft.name]) : __("Start a timesheet timer")
})

function errorText(e, fallback) {
	return e?.messages?.[0] || e?.message || fallback
}

async function discard(draft) {
	busy.value = "discard"
	try {
		setTimer(await call(`${API}.discard_timer_draft`, { name: draft.name }))
		notify.success(__("Draft {0} discarded", [draft.name]))
	} catch (e) {
		notify.error(errorText(e, __("Could not discard the draft")))
	} finally {
		busy.value = ""
	}
}

function settleStopRequest(stopped) {
	if (timer.stopRequest) {
		timer.stopRequest.resolve(stopped)
		timer.stopRequest = null
	}
}

function onStarted(next) {
	setTimer(next)
	notify.success(next.session?.project_name ? __("Timer started on {0}", [next.session.project_name]) : __("Timer started"))
}

function onStopped(response) {
	setTimer(response.state)
	notify.success(response.outcome?.name ? __("Timer stopped, {0} submitted", [response.outcome.name]) : __("Timer stopped, record submitted"))
	settleStopRequest(true)
}

function onLimit(response) {
	setTimer(response.state)
	showLimit.value = true
	settleStopRequest(false)
}

function onLimitDone(next, kind) {
	setTimer(next)
	notify.success(kind === "continue" ? __("Submitted with the available hours") : __("Account manager notified"))
}

function onResumed(next, withBreak) {
	setTimer(next)
	if (withBreak) notify.success(__("Break logged, timer running again"))
}

// A request from elsewhere (a Create menu) to start a timer.
watch(
	() => timer.startRequest,
	() => {
		if (state.value?.can_start) showStart.value = true
		else if (session.value) notify.error(__("A timer is already running. Stop it first."))
		else if (state.value?.blocking_drafts?.length) notify.error(blockTitle.value)
		else notify.error(__("Timers need an active Employee linked to your user."))
	}
)

// A request from elsewhere (the check-out guard) to stop the running timer.
watch(
	() => timer.stopRequest,
	(request) => {
		if (!request) return
		if (!session.value || session.value.state === "limit_exceeded") return settleStopRequest(true)
		showStop.value = true
	}
)
watch(showStop, (open) => {
	if (!open) setTimeout(() => settleStopRequest(false), 0) // closed without stopping
})

onMounted(() => (ticker = setInterval(() => (tick.value = Date.now()), 1000)))
onBeforeUnmount(() => clearInterval(ticker))
</script>
