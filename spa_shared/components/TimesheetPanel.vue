<template>
	<div class="tp">
		<div class="tp__row">
			<template v-if="!activeSession">
				<span class="tp__label" :title="projectLabel">
					{{ projectLabel || "No HR project configured" }}
				</span>
				<button
					type="button"
					class="tp__btn tp__btn--start"
					:disabled="!timesheetProject"
					@click="showStart = true"
				>
					<svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
					Start
				</button>
			</template>
			<template v-else>
				<span v-if="!isRunning && breakFrom" class="tp__pause-chip">
					{{ pauseLabel }}
				</span>
				<span
					class="tp__remaining-label"
					:class="`tp__remaining-label--${timeStatus.color}`"
				>
					{{ timeStatus.label }}
				</span>
				<button
					v-if="isRunning"
					type="button"
					class="tp__btn tp__btn--pause"
					@click="onPause"
				>
					<svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>
					Pause
				</button>
				<button
					v-else
					type="button"
					class="tp__btn tp__btn--resume"
					@click="onResume"
				>
					<svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
					Resume
				</button>
				<button type="button" class="tp__btn tp__btn--stop" @click="showStop = true">
					<svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><path d="M6 6h12v12H6z"/></svg>
					Stop
				</button>
			</template>
		</div>

		<ProjectStartModal
			v-if="showStart"
			:project-name="projectLabel"
			:project="timesheetProject"
			@confirm="onStartConfirm"
			@cancel="showStart = false"
		/>
		<StopModal v-if="showStop" @confirm="onStopConfirm" @cancel="showStop = false" />
		<BreakConfirm
			v-if="showBreakConfirm"
			:break-from="breakFrom"
			@confirm="onBreakConfirmYes"
			@skip="onBreakConfirmNo"
			@close="showBreakConfirm = false"
		/>
		<BreakModal
			v-if="showBreakModal"
			:break-from="breakFrom"
			@confirm="onBreakSubmit"
			@skip="onBreakSkip"
			@close="showBreakModal = false"
		/>
	</div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue"
import { call, toast } from "frappe-ui"
import {
	formatDurationShort,
	secondsSinceSystemDatetime,
} from "@spa/utils/datetime"
import BreakConfirm from "./timesheet/BreakConfirm.vue"
import BreakModal from "./timesheet/BreakModal.vue"
import ProjectStartModal from "./timesheet/ProjectStartModal.vue"
import StopModal from "./timesheet/StopModal.vue"

import spaConfig from "@/config"

const TIMER_API = spaConfig.timerApi
const SETTINGS_API = spaConfig.api

const timesheetProject = ref(null)
const projectLabel = ref("")
const activeSession = ref(null)
const elapsedSeconds = ref(0)
const pauseSeconds = ref(0)
const breakFrom = ref(null)
const showStart = ref(false)
const showStop = ref(false)
const showBreakConfirm = ref(false)
const showBreakModal = ref(false)

let timerInterval = null

const isRunning = computed(() => activeSession.value?.session_state === "running")
const expectedSeconds = computed(() => Number(activeSession.value?.expected_time) || 0)

const pauseLabel = computed(() => formatDurationShort(pauseSeconds.value))

const timeStatus = computed(() =>
	getTimeStatus(elapsedSeconds.value, expectedSeconds.value)
)

function getTimeStatus(elapsed, expected) {
	if (!expected || expected <= 0) {
		return { color: "neutral", label: "No expected time" }
	}
	const ratio = elapsed / expected
	const remaining = expected - elapsed
	let color = "neutral"
	if (ratio >= 1.2) color = "red"
	else if (ratio > 1) color = "orange"
	else if (ratio >= 0.8) color = "yellow"
	else if (ratio >= 0.6) color = "green"

	const label =
		remaining >= 0
			? `${formatDurationShort(remaining)} left`
			: `+${formatDurationShort(-remaining)} over`

	return {
		color,
		label,
	}
}

function apiErrorMessage(e) {
	if (e?.messages?.length) return e.messages[0]
	if (e?.message) return e.message
	return "Request failed"
}

function refreshElapsedFromSession() {
	if (!activeSession.value) return
	if (activeSession.value.session_state === "running") {
		const from = activeSession.value.from_time || activeSession.value.start_time
		if (from) {
			elapsedSeconds.value = secondsSinceSystemDatetime(from)
		}
	} else if (breakFrom.value) {
		pauseSeconds.value = secondsSinceSystemDatetime(breakFrom.value)
	}
}

function startTick() {
	clearInterval(timerInterval)
	refreshElapsedFromSession()
	timerInterval = setInterval(() => {
		if (!activeSession.value) return
		refreshElapsedFromSession()
	}, 1000)
}

function stopTick() {
	clearInterval(timerInterval)
	timerInterval = null
}

async function loadSettings() {
	const settings = await call(`${SETTINGS_API}.${spaConfig.settingsMethod}`)
	timesheetProject.value = settings[spaConfig.projectField]
	projectLabel.value =
		settings[spaConfig.projectNameField] || settings[spaConfig.projectField] || ""
}

async function loadSession() {
	const session = await call(`${TIMER_API}.get_active_project_session`)
	activeSession.value = session || null
	if (activeSession.value) {
		elapsedSeconds.value = activeSession.value.elapsed_seconds || 0
		if (activeSession.value.session_state === "paused") {
			breakFrom.value = activeSession.value.break_from || null
			pauseSeconds.value = breakFrom.value
				? secondsSinceSystemDatetime(breakFrom.value)
				: 0
		} else {
			breakFrom.value = null
			pauseSeconds.value = 0
		}
		startTick()
	} else {
		stopTick()
		elapsedSeconds.value = 0
		pauseSeconds.value = 0
		breakFrom.value = null
	}
}

async function onStartConfirm({ goal, expectedTime, manualStartTime, task }) {
	showStart.value = false
	if (!timesheetProject.value) {
		toast.error(`Configure ${spaConfig.label} timesheet project in phamos Settings.`)
		return
	}
	try {
		const args = {
			project_name: timesheetProject.value,
			expected_time: expectedTime,
			goal,
		}
		if (manualStartTime) args.manual_start_time = manualStartTime
		if (task) args.task = task
		const session = await call(`${TIMER_API}.start_project_timer`, args)
		activeSession.value = { ...session, expected_time: session.expected_time || expectedTime }
		elapsedSeconds.value = Math.max(0, session.elapsed_seconds || 0)
		breakFrom.value = null
		pauseSeconds.value = 0
		startTick()
		toast.success("Timer started")
	} catch (e) {
		toast.error(apiErrorMessage(e))
	}
}

async function onPause() {
	if (!activeSession.value) return
	try {
		const result = await call(`${TIMER_API}.pause_timer`, { name: activeSession.value.name })
		breakFrom.value = result?.break_from || null
		activeSession.value = { ...activeSession.value, session_state: "paused" }
		pauseSeconds.value = breakFrom.value ? secondsSinceSystemDatetime(breakFrom.value) : 0
	} catch (e) {
		toast.error(apiErrorMessage(e))
	}
}

async function onResume() {
	if (!activeSession.value) return
	if (breakFrom.value) {
		showBreakConfirm.value = true
		return
	}
	await doResume()
}

async function doResume() {
	try {
		await call(`${TIMER_API}.resume_timer`, { name: activeSession.value.name })
		activeSession.value = { ...activeSession.value, session_state: "running" }
		breakFrom.value = null
		pauseSeconds.value = 0
	} catch (e) {
		toast.error(apiErrorMessage(e))
		await loadSession()
	}
}

function onBreakConfirmYes() {
	showBreakConfirm.value = false
	showBreakModal.value = true
}

async function onBreakConfirmNo() {
	showBreakConfirm.value = false
	breakFrom.value = null
	pauseSeconds.value = 0
	await doResume()
}

async function onBreakSubmit({ project, activityType, goal, result, percentBillable }) {
	showBreakModal.value = false
	try {
		await call(`${TIMER_API}.create_break_timesheet`, {
			from_time: breakFrom.value,
			project,
			goal,
			result,
			percent_billable: percentBillable,
			activity_type: activityType || null,
		})
		breakFrom.value = null
		pauseSeconds.value = 0
		await doResume()
		toast.success("Break timesheet submitted")
	} catch (e) {
		toast.error(apiErrorMessage(e))
		await loadSession()
	}
}

async function onBreakSkip() {
	showBreakModal.value = false
	breakFrom.value = null
	pauseSeconds.value = 0
	await doResume()
}

async function onStopConfirm({ result, percentBillable, manualEndTime, activityType }) {
	showStop.value = false
	if (!activeSession.value) return
	try {
		const args = {
			name: activeSession.value.name,
			result,
			percent_billable: percentBillable,
			activity_type: activityType,
		}
		if (manualEndTime) args.manual_end_time = manualEndTime
		await call(`${TIMER_API}.stop_timer`, args)
		stopTick()
		activeSession.value = null
		elapsedSeconds.value = 0
		pauseSeconds.value = 0
		breakFrom.value = null
		toast.success("Session submitted")
	} catch (e) {
		toast.error(apiErrorMessage(e))
		await loadSession()
	}
}

onMounted(async () => {
	await loadSettings()
	await loadSession()
})

onUnmounted(() => {
	stopTick()
})
</script>

<style scoped>
.tp {
	min-width: 0;
	max-width: 560px;
}
.tp__row {
	display: flex;
	align-items: center;
	flex-wrap: wrap;
	gap: 6px;
}
.tp__label {
	max-width: 140px;
	font-size: 12px;
	color: var(--text-muted, #6b7280);
	overflow: hidden;
	text-overflow: ellipsis;
	white-space: nowrap;
}
.tp__pause-chip {
	font-size: 12px;
	font-weight: 700;
	font-variant-numeric: tabular-nums;
	color: #a16207;
	background: #fefce8;
	border: 1px solid #fef08a;
	border-radius: 12px;
	padding: 2px 8px;
	white-space: nowrap;
}
.tp__remaining-label {
	font-size: 12px;
	font-weight: 700;
	white-space: nowrap;
}
.tp__remaining-label--neutral { color: #6b7280; }
.tp__remaining-label--green { color: #16a34a; }
.tp__remaining-label--yellow { color: #ca8a04; }
.tp__remaining-label--orange { color: #ea580c; }
.tp__remaining-label--red { color: #dc2626; }

.tp__btn {
	display: inline-flex;
	align-items: center;
	gap: 5px;
	padding: 5px 11px;
	border-radius: 6px;
	font-size: 12px;
	font-weight: 600;
	cursor: pointer;
	border: 1px solid transparent;
	transition: background 0.12s, border-color 0.12s;
	white-space: nowrap;
	line-height: 1;
}
.tp__btn:disabled {
	opacity: 0.55;
	cursor: not-allowed;
}
.tp__btn--start { background: #15803d; color: #fff; border-color: #15803d; }
.tp__btn--start:hover:not(:disabled) { background: #166534; }
.tp__btn--pause { background: #fefce8; color: #a16207; border-color: #fef08a; }
.tp__btn--pause:hover { background: #fef9c3; }
.tp__btn--resume { background: #f0fdf4; color: #15803d; border-color: #bbf7d0; }
.tp__btn--resume:hover { background: #dcfce7; }
.tp__btn--stop { background: #fef2f2; color: #dc2626; border-color: #fecaca; }
.tp__btn--stop:hover { background: #fee2e2; border-color: #f87171; }

@media (prefers-color-scheme: dark) {
	.tp__pause-chip {
		color: #fbbf24;
		background: rgba(251, 191, 36, 0.12);
		border-color: rgba(251, 191, 36, 0.35);
	}
	.tp__remaining-label--neutral { color: #9ca3af; }
	.tp__remaining-label--green { color: #4ade80; }
	.tp__remaining-label--yellow { color: #facc15; }
	.tp__remaining-label--orange { color: #fb923c; }
	.tp__remaining-label--red { color: #f87171; }
	.tp__btn--pause { background: rgba(251, 191, 36, 0.12); color: #fbbf24; border-color: rgba(251, 191, 36, 0.35); }
	.tp__btn--pause:hover { background: rgba(251, 191, 36, 0.2); }
	.tp__btn--resume { background: rgba(34, 197, 94, 0.12); color: #4ade80; border-color: rgba(34, 197, 94, 0.35); }
	.tp__btn--resume:hover { background: rgba(34, 197, 94, 0.2); }
	.tp__btn--stop { background: rgba(248, 113, 113, 0.12); color: #f87171; border-color: rgba(248, 113, 113, 0.35); }
	.tp__btn--stop:hover { background: rgba(248, 113, 113, 0.2); border-color: #f87171; }
}
</style>
