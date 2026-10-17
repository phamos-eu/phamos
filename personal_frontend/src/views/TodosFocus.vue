<template>
	<div class="h-full min-h-0 overflow-y-auto bg-surface-gray-1 p-5">
		<!-- Running session -->
		<div v-if="session" class="mx-auto flex max-w-6xl flex-col gap-5">
			<div class="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-outline-gray-2 bg-surface-white px-5 py-3">
				<div class="flex items-baseline gap-3">
					<span
						class="font-mono text-3xl font-semibold tabular-nums"
						:class="clock?.overtime ? 'text-ink-amber-3' : 'text-ink-gray-9'"
						role="timer"
						:aria-label="clockLabel"
					>
						{{ clockText }}
					</span>
					<span class="text-sm text-ink-gray-5">{{ clockCaption }}</span>
				</div>
				<div class="flex items-center gap-3 text-sm text-ink-gray-6">
					<span>{{ __("{0} of {1} done", [session.done_count, session.items.length]) }}</span>
					<Button variant="subtle" @click="openBreakOut">{{ __("Leave focus") }}</Button>
				</div>
			</div>

			<div
				v-if="clock?.overtime"
				class="rounded-lg border border-outline-amber-2 bg-surface-amber-1 px-4 py-2 text-sm text-ink-amber-4"
			>
				{{ __("Time is up. Finish the step you are on, then mark it done or park it with a note.") }}
			</div>

			<div class="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_18rem]">
				<section class="min-w-0 rounded-lg border border-outline-gray-2 bg-surface-white p-5">
					<template v-if="current">
						<div class="mb-1 text-xs font-medium uppercase tracking-wide text-ink-gray-5">{{ __("Now") }}</div>
						<h2 class="text-xl font-semibold text-ink-gray-9">{{ current.summary || current.todo }}</h2>
						<div class="mt-1 flex flex-wrap gap-x-3 text-xs text-ink-gray-5">
							<span>{{ __("{0} on this ToDo", [minutesLabel(currentMinutes)]) }}</span>
							<span v-if="detail?.estimate_minutes">{{ __("estimate {0}", [minutesLabel(detail.estimate_minutes)]) }}</span>
							<span v-if="detail?.date" :class="detail.overdue ? 'text-ink-red-3' : ''">{{ __("due {0}", [formatDate(detail.date)]) }}</span>
							<a v-if="detail?.reference_url" :href="detail.reference_url" target="_blank" class="hover:underline">
								{{ __(detail.reference_type) }} {{ detail.reference_title || detail.reference_name }}
							</a>
						</div>

						<div
							v-if="detail?.resume_note"
							class="mt-4 rounded-md border border-outline-gray-2 bg-surface-gray-1 px-3 py-2 text-sm text-ink-gray-8"
						>
							<span class="text-xs font-medium text-ink-gray-5">{{ __("Where you left off") }}</span>
							<p class="whitespace-pre-line">{{ detail.resume_note }}</p>
						</div>

						<div v-if="detail && hasDescriptionBody" class="mt-4">
							<TextEditor :content="detail.description" :editable="false" editor-class="prose-sm max-w-none text-ink-gray-8" />
						</div>

						<div v-if="detail" class="mt-4">
							<LinkedChecklistsSection
								:key="detail.name"
								document="ToDo"
								:reference-record="detail.name"
								:reference-title="detail.summary"
								:allow-create="true"
							/>
						</div>

						<div class="mt-5 flex flex-wrap gap-2">
							<Button variant="solid" :loading="acting === 'done'" @click="markDone">
								<template #prefix><FeatherIcon name="check" class="h-4 w-4" /></template>
								{{ __("Done") }}
							</Button>
							<Button :disabled="Boolean(acting)" @click="openPark">{{ __("Park it") }}</Button>
						</div>
					</template>
					<div v-else class="flex flex-col items-start gap-3">
						<h2 class="text-lg font-semibold text-ink-gray-9">{{ __("Everything here is done or parked.") }}</h2>
						<p class="text-sm text-ink-gray-6">{{ __("Pick a parked ToDo to continue, or end the session.") }}</p>
						<Button variant="solid" :loading="acting === 'end'" @click="finish">{{ __("End the session") }}</Button>
					</div>
				</section>

				<aside class="flex flex-col gap-5">
					<section class="rounded-lg border border-outline-gray-2 bg-surface-white p-4">
						<h3 class="mb-2 text-sm font-semibold text-ink-gray-9">{{ __("In this session") }}</h3>
						<ol class="space-y-1">
							<li v-for="(item, index) in session.items" :key="item.todo">
								<button
									type="button"
									class="flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left text-sm transition"
									:class="item.current ? 'bg-surface-gray-3' : 'hover:bg-surface-gray-2'"
									:disabled="item.done || item.current || Boolean(acting)"
									:aria-current="item.current ? 'step' : undefined"
									@click="switchTo(item)"
								>
									<FeatherIcon :name="itemIcon(item)" class="mt-0.5 h-4 w-4 flex-none" :class="itemIconClass(item)" />
									<span class="min-w-0 flex-1">
										<span class="block truncate" :class="item.done ? 'text-ink-gray-5 line-through' : 'text-ink-gray-9'">
											{{ index + 1 }}. {{ item.summary || item.todo }}
										</span>
										<span v-if="item.minutes || item.parked" class="text-xs text-ink-gray-5">
											{{ item.parked ? __("parked · {0}", [minutesLabel(item.minutes)]) : minutesLabel(item.minutes) }}
										</span>
									</span>
								</button>
							</li>
						</ol>
					</section>

					<section class="rounded-lg border border-outline-gray-2 bg-surface-white p-4">
						<h3 class="mb-1 text-sm font-semibold text-ink-gray-9">{{ __("Capture for later") }}</h3>
						<p class="mb-2 text-xs text-ink-gray-5">{{ __("A thought or a new task: write it down and stay on track.") }}</p>
						<form class="flex gap-2" @submit.prevent="capture">
							<FormControl v-model="captureText" type="text" size="sm" class="min-w-0 flex-1" :placeholder="__('New ToDo…')" />
							<Button type="submit" size="sm" :disabled="!captureText.trim()" :loading="capturing">{{ __("Add") }}</Button>
						</form>
					</section>
				</aside>
			</div>
		</div>

		<!-- No session -->
		<div v-else class="mx-auto flex max-w-3xl flex-col gap-5">
			<section v-if="lastEnded" class="rounded-lg border border-outline-gray-2 bg-surface-white p-5">
				<h2 class="text-lg font-semibold text-ink-gray-9">{{ endedTitle }}</h2>
				<p class="mt-1 text-sm text-ink-gray-6">{{ endedText }}</p>
				<div class="mt-4 flex gap-2">
					<Button variant="solid" @click="router.push({ name: 'Todos' })">{{ __("Back to the dashboard") }}</Button>
					<Button @click="showStart = true">{{ __("Another session") }}</Button>
				</div>
			</section>
			<section v-else class="rounded-lg border border-outline-gray-2 bg-surface-white p-5">
				<h2 class="text-lg font-semibold text-ink-gray-9">{{ __("Focus on a few ToDos") }}</h2>
				<p class="mt-1 text-sm text-ink-gray-6">
					{{
						__(
							"Choose up to five ToDos and a length. Until you finish or leave, the cockpit shows only them. Leaving is always possible."
						)
					}}
				</p>
				<Button class="mt-4" variant="solid" @click="showStart = true">{{ __("Start a focus session") }}</Button>
			</section>

			<section v-if="history.length" class="rounded-lg border border-outline-gray-2 bg-surface-white p-5">
				<h3 class="mb-2 text-sm font-semibold text-ink-gray-9">{{ __("Recent sessions") }}</h3>
				<ul class="divide-y divide-outline-gray-1 text-sm">
					<li v-for="row in history" :key="row.name" class="flex items-center justify-between gap-3 py-2">
						<span class="text-ink-gray-8">{{ formatDatetime(row.started_at) }}</span>
						<span class="text-ink-gray-6">{{ __("{0} of {1} done", [row.done, row.total]) }} · {{ OUTCOME_LABEL[row.outcome] ? __(OUTCOME_LABEL[row.outcome]) : row.outcome }}</span>
					</li>
				</ul>
			</section>
		</div>

		<StartFocusDialog v-model="showStart" />

		<Dialog v-model="showPark" :options="{ title: __('Park this ToDo'), size: 'md' }">
			<template #body-content>
				<div class="space-y-4">
					<FormControl
						v-model="parkNote"
						type="textarea"
						size="sm"
						:label="__('Where will you pick it up?')"
						:placeholder="__('The next concrete step, so restarting is easy.')"
					/>
					<ErrorMessage :message="dialogError" />
					<div class="flex justify-end gap-2">
						<Button variant="ghost" @click="showPark = false">{{ __("Cancel") }}</Button>
						<Button variant="solid" :loading="acting === 'park'" @click="park">{{ __("Park and continue") }}</Button>
					</div>
				</div>
			</template>
		</Dialog>

		<Dialog v-model="showBreakOut" :options="{ title: __('Leave focus?'), size: 'md' }">
			<template #body-content>
				<div class="space-y-4">
					<p v-if="!breakOutWaitTotal" class="text-sm text-ink-gray-6">
						{{ __("You just started, so leaving costs nothing.") }}
					</p>
					<template v-else>
						<p class="text-sm text-ink-gray-6">
							{{ __("Before you go: why, and where will you pick up? Your note is kept on the ToDo.") }}
						</p>
						<FormControl v-model="breakReason" type="select" size="sm" :label="__('Why leave now?')" :options="BREAK_REASONS.map((reason) => ({ label: __(reason), value: reason }))" />
						<FormControl
							v-if="current"
							v-model="breakNote"
							type="textarea"
							size="sm"
							:label="__('Where to pick up')"
							:placeholder="__('Next step for “{0}”', [current.summary])"
						/>
					</template>
					<ErrorMessage :message="dialogError" />
					<div class="flex justify-end gap-2">
						<Button variant="solid" @click="showBreakOut = false">{{ __("Stay focused") }}</Button>
						<Button
							variant="subtle"
							:disabled="breakOutCountdown > 0"
							:loading="acting === 'leave'"
							@click="leave"
						>
							{{ breakOutCountdown > 0 ? __("Leave in {0} s", [breakOutCountdown]) : __("Leave focus") }}
						</Button>
					</div>
				</div>
			</template>
		</Dialog>
	</div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { useRouter } from "vue-router"
import { call, TextEditor } from "frappe-ui"
import { notify } from "@spa/utils/notify.js"
import LinkedChecklistsSection from "@spa/components/LinkedChecklistsSection.vue"
import { formatDate, formatDatetime } from "@spa/utils/datetime.js"
import { __ } from "@spa/utils/i18n.js"
import { activeItem, breakOutWait, formatClock, sessionClock } from "@spa/utils/focusRules.js"
import spaConfig from "@/config"
import StartFocusDialog from "@/components/StartFocusDialog.vue"
import { focus, loadFocus, setFocus } from "@/focusStore.js"

const API = spaConfig.api
const BREAK_REASONS = ["Something urgent came up", "A meeting starts", "Wrong ToDos picked", "Need a break", "Other"]
const OUTCOME_LABEL = { Completed: "completed", "Broke out": "left early", Expired: "timed out" }

const router = useRouter()
const tick = ref(Date.now())
let timer = null

const session = computed(() => focus.session)
const current = computed(() => activeItem(session.value))
const detail = ref(null)
const acting = ref("")
const history = ref([])
const lastEnded = ref(null)
const showStart = ref(false)

const showPark = ref(false)
const parkNote = ref("")
const showBreakOut = ref(false)
const breakReason = ref(BREAK_REASONS[0])
const breakNote = ref("")
const breakOutWaitTotal = ref(0)
const breakOutOpenedAt = ref(0)
const dialogError = ref("")

const captureText = ref("")
const capturing = ref(false)

const localElapsed = computed(() => Math.max(0, (tick.value - focus.loadedAt) / 1000))
const clock = computed(() => sessionClock(session.value, localElapsed.value))
const clockText = computed(() => {
	if (!clock.value) return ""
	return clock.value.mode === "stopwatch" ? formatClock(clock.value.elapsed) : formatClock(clock.value.remaining)
})
const clockCaption = computed(() => {
	if (!clock.value) return ""
	if (clock.value.mode === "stopwatch") return __("in focus")
	return clock.value.overtime ? __("time is up") : __("left")
})
const clockLabel = computed(() => {
	if (!clock.value) return ""
	if (clock.value.mode === "stopwatch") return __("{0} in focus", [clockText.value])
	return clock.value.overtime ? __("{0}, time is up", [clockText.value]) : __("{0} left", [clockText.value])
})
const currentMinutes = computed(() => {
	const item = current.value
	if (!item) return 0
	return item.current ? item.minutes + Math.floor(localElapsed.value / 60) : item.minutes
})
const hasDescriptionBody = computed(() => {
	const text = (detail.value?.description || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim()
	return text.length > (detail.value?.summary || "").length + 1
})
const breakOutCountdown = computed(() => {
	if (!breakOutWaitTotal.value) return 0
	const passed = Math.floor((tick.value - breakOutOpenedAt.value) / 1000)
	return Math.max(0, breakOutWaitTotal.value - passed)
})
const endedTitle = computed(() => {
	const ended = lastEnded.value
	if (!ended) return ""
	if (ended.outcome === "Completed" && ended.done_count === ended.items.length) return __("Session complete.")
	return ended.done_count ? __("Session ended. Good progress.") : __("Session ended.")
})
const endedText = computed(() => {
	const ended = lastEnded.value
	if (!ended) return ""
	const minutes = ended.items.reduce((sum, item) => sum + (item.minutes || 0), 0)
	return ended.done_count === 1
		? __("1 ToDo done in {0}.", [minutesLabel(minutes)])
		: __("{0} ToDos done in {1}.", [ended.done_count, minutesLabel(minutes)])
})

function minutesLabel(minutes) {
	const m = Math.max(0, Math.round(minutes || 0))
	if (m < 60) return __("{0} min", [m])
	return m % 60 ? __("{0} h {1} min", [Math.floor(m / 60), m % 60]) : __("{0} h", [Math.floor(m / 60)])
}

function itemIcon(item) {
	if (item.done) return "check-circle"
	if (item.parked) return "pause-circle"
	if (item.current) return "play-circle"
	return "circle"
}

function itemIconClass(item) {
	if (item.done) return "text-ink-green-3"
	if (item.current) return "text-ink-gray-9"
	return "text-ink-gray-4"
}

function errorText(e, fallback) {
	return e?.messages?.[0] || e?.message || fallback
}

async function loadDetail() {
	const name = current.value?.todo
	if (!name) {
		detail.value = null
		return
	}
	if (detail.value?.name === name) return
	try {
		detail.value = await call(`${API}.get_todo`, { name })
	} catch {
		detail.value = { name, summary: current.value.summary, description: "" }
	}
}

async function act(kind, method, args) {
	acting.value = kind
	dialogError.value = ""
	try {
		const result = await call(`${API}.${method}`, args)
		apply(result)
		return true
	} catch (e) {
		dialogError.value = errorText(e, __("That did not work"))
		if (!showPark.value && !showBreakOut.value) notify.error(dialogError.value)
		return false
	} finally {
		acting.value = ""
	}
}

function apply(result) {
	if (result && result.status === "Ended") {
		lastEnded.value = result
		setFocus(null)
		loadHistory()
	} else {
		setFocus(result)
	}
}

async function markDone() {
	const name = current.value.todo
	if (await act("done", "focus_mark_done", { todo: name })) {
		detail.value = null
		notify.success(__("Done. One less."))
	}
}

function openPark() {
	parkNote.value = detail.value?.resume_note || ""
	dialogError.value = ""
	showPark.value = true
}

async function park() {
	if (await act("park", "focus_park", { todo: current.value.todo, resume_note: parkNote.value })) {
		showPark.value = false
		detail.value = null
	}
}

async function switchTo(item) {
	if (await act("switch", "focus_switch", { todo: item.todo })) detail.value = null
}

async function finish() {
	await act("end", "end_focus", { outcome: "Completed" })
}

function openBreakOut() {
	dialogError.value = ""
	breakNote.value = ""
	breakReason.value = BREAK_REASONS[0]
	breakOutWaitTotal.value = breakOutWait(clock.value?.elapsed || 0, session.value)
	breakOutOpenedAt.value = Date.now()
	showBreakOut.value = true
}

async function leave() {
	const ok = await act("leave", "end_focus", {
		outcome: "Broke out",
		reason: breakOutWaitTotal.value ? breakReason.value : "Left in the first minute",
		resume_note: breakNote.value || null,
	})
	if (ok) showBreakOut.value = false
}

async function capture() {
	const text = captureText.value.trim()
	if (!text) return
	capturing.value = true
	try {
		await call(`${API}.create_todo`, { description: text })
		captureText.value = ""
		notify.success(__("Captured for later."))
	} catch (e) {
		notify.error(errorText(e, __("Could not capture the ToDo")))
	} finally {
		capturing.value = false
	}
}

async function loadHistory() {
	try {
		history.value = await call(`${API}.get_focus_history`, { limit: 5 })
	} catch {
		history.value = []
	}
}

watch(() => current.value?.todo, loadDetail, { immediate: true })
watch(session, (value, previous) => {
	// Ended in another tab: show the summary there too.
	if (!value && previous && !lastEnded.value) loadHistory()
})

onMounted(async () => {
	timer = setInterval(() => (tick.value = Date.now()), 1000)
	await loadFocus()
	if (!focus.session) loadHistory()
})

onBeforeUnmount(() => clearInterval(timer))
</script>
