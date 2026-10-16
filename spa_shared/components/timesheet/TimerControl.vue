<template>
	<div v-if="state?.available" class="flex items-center gap-1">
		<!-- Idle -->
		<template v-if="!session">
			<Button
				size="sm"
				variant="ghost"
				:disabled="!state.can_start"
				:title="blockTitle"
				@click="showStart = true"
			>
				<template #prefix><FeatherIcon name="play" class="h-4 w-4" /></template>
				Start timer
			</Button>
			<Button
				v-if="state.blocking_drafts?.length"
				size="sm"
				variant="ghost"
				:title="`Discard the empty draft ${state.blocking_drafts[0].name}`"
				:loading="busy === 'discard'"
				@click="discard(state.blocking_drafts[0])"
			>
				Discard draft
			</Button>
		</template>

		<!-- Waiting for the time-limit decision -->
		<Button v-else-if="session.state === 'limit_exceeded'" size="sm" variant="subtle" theme="orange" @click="showLimit = true">
			<template #prefix><FeatherIcon name="alert-triangle" class="h-4 w-4" /></template>
			Time limit
		</Button>

		<!-- Running or paused -->
		<template v-else>
			<Popover placement="bottom-end">
				<template #target="{ togglePopover }">
					<button
						type="button"
						class="flex h-7 items-center gap-2 rounded px-2 text-sm hover:bg-surface-gray-2"
						:aria-label="`${session.state === 'running' ? 'Timer running' : 'Timer paused'}, ${clock}, ${session.project_name}`"
						@click="togglePopover"
					>
						<span
							class="font-mono tabular-nums"
							:class="session.state === 'running' ? 'text-ink-green-3' : 'text-ink-amber-3'"
							role="timer"
						>
							{{ clock }}
						</span>
						<span class="hidden max-w-[12rem] truncate text-ink-gray-7 md:inline">{{ session.project_name }}</span>
					</button>
				</template>
				<template #body-main>
					<div class="w-72 space-y-2 p-3 text-sm">
						<div class="font-medium text-ink-gray-9">{{ session.project_name }}</div>
						<div class="text-ink-gray-7">{{ session.goal }}</div>
						<div v-if="session.task_subject" class="text-xs text-ink-gray-5">Task: {{ session.task_subject }}</div>
						<div v-if="session.gitlab_issue_title" class="text-xs text-ink-gray-5">Issue: {{ session.gitlab_issue_title }}</div>
						<div class="flex justify-between text-xs text-ink-gray-6">
							<span>Started {{ formatTime(session.from_time) }}</span>
							<span :class="over ? 'text-ink-red-4' : ''">{{ budget }}</span>
						</div>
						<div v-if="session.state === 'paused'" class="text-xs text-ink-amber-4">On a break for {{ breakText }}</div>
						<button type="button" class="text-xs text-ink-gray-5 hover:underline" @click="openDesk(session.desk_url)">
							Open the record in Desk ↗
						</button>
					</div>
				</template>
			</Popover>
			<!-- Plain buttons: frappe-ui's Button drops aria-label on icon-only buttons. -->
			<button
				v-if="session.state === 'running'"
				type="button"
				class="flex h-7 w-7 items-center justify-center rounded text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-9 disabled:opacity-50"
				aria-label="Pause the timer"
				title="Pause"
				:disabled="busy === 'pause'"
				@click="pause"
			>
				<FeatherIcon name="pause" class="h-4 w-4" />
			</button>
			<button v-else type="button" class="flex h-7 w-7 items-center justify-center rounded text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-9 disabled:opacity-50" aria-label="Resume the timer" title="Resume" @click="showBreak = true">
				<FeatherIcon name="play" class="h-4 w-4" />
			</button>
			<button type="button" class="flex h-7 w-7 items-center justify-center rounded text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-9 disabled:opacity-50" aria-label="Stop the timer" title="Stop" @click="showStop = true">
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
		<BreakDialog v-model="showBreak" :session="session" :break-seconds="breakSeconds" @resumed="onResumed" />
		<TimeLimitDialog v-model="showLimit" :session="session" @done="onLimitDone" />
	</div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { call, Popover } from "frappe-ui"
import { openDesk } from "@spa/utils/appWindow.js"
import { formatTime as formatTimeFull } from "@spa/utils/datetime.js"
import { notify } from "@spa/utils/notify.js"
import { budgetText, formatClock, formatMinutes, isOverBudget, liveBreak, liveElapsed } from "@spa/utils/timerClock.js"
import { setTimer, timer, loadTimer } from "@spa/timerStore.js"
import spaConfig from "@/config"
import BreakDialog from "./BreakDialog.vue"
import StartTimerDialog from "./StartTimerDialog.vue"
import StopTimerDialog from "./StopTimerDialog.vue"
import TimeLimitDialog from "./TimeLimitDialog.vue"

const API = spaConfig.api
const tick = ref(Date.now())
const busy = ref("")
const showStart = ref(false)
const showStop = ref(false)
const showBreak = ref(false)
const showLimit = ref(false)
let ticker = null

const formatTime = (value) => formatTimeFull(value).slice(0, 5)
const state = computed(() => timer.state)
const session = computed(() => state.value?.session || null)
const sinceLoad = computed(() => (tick.value - timer.loadedAt) / 1000)
const elapsed = computed(() => liveElapsed(session.value, sinceLoad.value))
const clock = computed(() => formatClock(elapsed.value))
const budget = computed(() => budgetText(session.value, elapsed.value))
const over = computed(() => isOverBudget(session.value, elapsed.value))
const breakSeconds = computed(() => liveBreak(session.value, state.value?.server_now, sinceLoad.value))
const breakText = computed(() => formatMinutes(breakSeconds.value))
const blockTitle = computed(() => {
	const draft = state.value?.blocking_drafts?.[0]
	return draft ? `Finish or discard the empty draft ${draft.name} first` : "Start a timesheet timer"
})

function errorText(e, fallback) {
	return e?.messages?.[0] || e?.message || fallback
}

async function pause() {
	busy.value = "pause"
	try {
		setTimer(await call(`${API}.pause_timer`, { name: session.value.name }))
	} catch (e) {
		notify.error(errorText(e, "Could not pause the timer"))
		loadTimer()
	} finally {
		busy.value = ""
	}
}

async function discard(draft) {
	busy.value = "discard"
	try {
		setTimer(await call(`${API}.discard_timer_draft`, { name: draft.name }))
		notify.success(`Draft ${draft.name} discarded`)
	} catch (e) {
		notify.error(errorText(e, "Could not discard the draft"))
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
	notify.success(`Timer started on ${next.session?.project_name || "the project"}`)
}

function onStopped(response) {
	setTimer(response.state)
	notify.success(`Timer stopped, ${response.outcome?.name || "record"} submitted`)
	settleStopRequest(true)
}

function onLimit(response) {
	setTimer(response.state)
	showLimit.value = true
	settleStopRequest(false)
}

function onLimitDone(next, kind) {
	setTimer(next)
	notify.success(kind === "continue" ? "Submitted with the available hours" : "Account manager notified")
}

function onResumed(next, withBreak) {
	setTimer(next)
	if (withBreak) notify.success("Break logged, timer running again")
}

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
