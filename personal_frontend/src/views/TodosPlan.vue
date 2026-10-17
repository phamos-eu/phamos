<template>
	<!-- My Day as a timeline (#1573): the days run from the future at the top, through today, into
	     the past below. Within a day the hours read from morning to evening. -->
	<div class="relative h-full min-h-0">
		<div ref="scroller" class="h-full min-h-0 overflow-y-auto bg-surface-gray-1">
			<!-- Unread Issue chats stay in view while the days scroll by (#1618). -->
			<div class="sticky top-0 z-10 mx-auto max-w-5xl px-5 pt-3 empty:hidden">
				<UnreadIssueChats />
			</div>
			<div class="mx-auto max-w-5xl px-5 pb-16">
				<div ref="topSentinel" class="py-3 text-center text-xs text-ink-gray-5">
					{{ loadingLater ? __("Loading later days…") : to >= lastFuture ? __("Plan further ahead in the list.") : "" }}
				</div>
				<div v-if="error" class="mb-3 rounded-lg border border-outline-gray-2 bg-surface-red-1 p-3 text-sm text-ink-red-4">{{ error }}</div>
				<TimelineDay
					v-for="date in dates"
					:key="date"
					:date="date"
					:day="days[date] || {}"
					:events="eventsByDay[date] || []"
					:today="today"
					:now-minute="nowMinute"
					:active="date === activeDate"
					@open-date="goTo"
					@changed="reloadAround(today)"
				/>
				<div ref="bottomSentinel" class="py-6 text-center text-xs text-ink-gray-5">
					{{ loadingEarlier ? __("Loading earlier days…") : hasEarlier ? "" : __("Nothing earlier.") }}
				</div>
			</div>
		</div>
		<Button class="absolute bottom-5 right-5 shadow" variant="solid" :title="__('Jump to today (T)')" @click="goTo(today)">
			<template #prefix><FeatherIcon name="crosshair" class="h-4 w-4" /></template>
			{{ __("Today") }}
		</Button>
	</div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { call } from "frappe-ui"
import { useScrollSentinels } from "@spa/composables/useScrollSentinels.js"
import { useUserRealtime } from "@spa/composables/useUserRealtime.js"
import { parseSystemDatetimeToUserDate, todayIsoInUserTz } from "@spa/utils/datetime.js"
import { dayKey, minuteOfDay, splitIntoDays } from "@spa/utils/timelineLayout.js"
import { __ } from "@spa/utils/i18n.js"
import spaConfig from "@/config"
import TimelineDay from "@/components/TimelineDay.vue"
import UnreadIssueChats from "@/components/UnreadIssueChats.vue"

const API = spaConfig.api
const AROUND = 3
const STEP = 7
const FUTURE_DAYS = 30
const MAX_CALL = 31

const route = useRoute()
const router = useRouter()
const scroller = ref(null)
const topSentinel = ref(null)
const bottomSentinel = ref(null)

const today = ref(todayIsoInUserTz())
const from = ref("")
const to = ref("")
const days = ref({}) // date -> { checkins, todos_done, plan }
const timeLogs = ref({}) // name -> log
const hasEarlier = ref(true)
const loadingEarlier = ref(false)
const loadingLater = ref(false)
const error = ref("")
const now = ref(new Date())
const activeDate = ref("")
let ticker = null
let scrollFrame = 0

// The day whose section is at the top of the view; its date is shown larger.
function updateActiveDate() {
	scrollFrame = 0
	const el = scroller.value
	if (!el) return
	const top = el.getBoundingClientRect().top + 4
	for (const section of el.querySelectorAll("section[id^='day-']")) {
		const rect = section.getBoundingClientRect()
		if (rect.top <= top && rect.bottom > top) {
			activeDate.value = section.id.slice(4)
			return
		}
	}
	activeDate.value = ""
}

function onScroll() {
	if (!scrollFrame) scrollFrame = requestAnimationFrame(updateActiveDate)
}

const lastFuture = computed(() => addDays(today.value, FUTURE_DAYS))
const nowMinute = computed(() => minuteOfDay(now.value))
const dates = computed(() => {
	const list = []
	if (!from.value || !to.value) return list
	for (let d = to.value; d >= from.value; d = addDays(d, -1)) list.push(d) // newest first
	return list
})

function addDays(iso, n) {
	const [y, m, d] = iso.split("-").map(Number)
	return dayKey(new Date(y, m - 1, d + n))
}

function local(value) {
	return value ? parseSystemDatetimeToUserDate(String(value)) : null
}

// All events of the loaded window, placed on the user's local days.
const eventsByDay = computed(() => {
	const items = []
	for (const day of Object.values(days.value)) {
		for (const c of day.checkins || []) {
			items.push({
				id: `ci-${c.name}`,
				name: c.name,
				kind: "point",
				type: "checkin",
				start: local(c.time),
				end: null,
				label: c.log_type === "IN" ? __("Checked in") : __("Checked out"),
				icon: c.log_type === "IN" ? "log-in" : "log-out",
				iconClass: c.log_type === "IN" ? "text-ink-green-3" : "text-ink-gray-5",
				title: c.device_id
					? c.log_type === "IN" ? __("Check-in · {0}", [c.device_id]) : __("Check-out · {0}", [c.device_id])
					: c.log_type === "IN" ? __("Check-in") : __("Check-out"),
			})
		}
		for (const t of day.todos_done || []) {
			items.push({
				id: `td-${t.name}`,
				name: t.name,
				kind: "point",
				type: "todo",
				start: local(t.closed_on),
				end: null,
				label: t.summary,
				icon: "check",
				iconClass: "text-ink-green-3",
				important: t.important,
				title: t.planned ? __("Planned: {0}", [t.summary]) : __("Spontaneous: {0}", [t.summary]),
			})
		}
	}
	for (const log of Object.values(timeLogs.value)) {
		log.segments.forEach((segment, index) => {
			items.push({
				id: `tl-${log.name}-${index}`,
				kind: segment.kind,
				start: local(segment.from_time),
				end: local(segment.to_time),
				log,
			})
		})
	}
	return splitIntoDays(items, now.value)
})

function merge(data) {
	const next = { ...days.value }
	for (const day of data.days) next[String(day.date)] = day
	days.value = next
	const logs = { ...timeLogs.value }
	for (const log of data.time_logs) logs[log.name] = log
	timeLogs.value = logs
}

async function fetchRange(start, end) {
	const chunks = []
	for (let s = start; s <= end; s = addDays(s, MAX_CALL)) {
		const e = addDays(s, MAX_CALL - 1) < end ? addDays(s, MAX_CALL - 1) : end
		chunks.push(call(`${API}.get_timeline`, { from_date: s, to_date: e }))
	}
	const results = await Promise.all(chunks)
	results.forEach(merge)
	return results[0]
}

async function loadEarlier() {
	if (loadingEarlier.value || !hasEarlier.value || !from.value) return
	loadingEarlier.value = true
	try {
		const start = addDays(from.value, -STEP)
		const first = await fetchRange(start, addDays(from.value, -1))
		hasEarlier.value = first.has_earlier
		from.value = start
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || __("Could not load earlier days")
	} finally {
		loadingEarlier.value = false
		sentinels.recheck()
	}
}

async function loadLater() {
	if (loadingLater.value || !to.value || to.value >= lastFuture.value) return
	loadingLater.value = true
	const el = scroller.value
	const before = el ? el.scrollHeight - el.scrollTop : 0
	try {
		const end = addDays(to.value, STEP) < lastFuture.value ? addDays(to.value, STEP) : lastFuture.value
		await fetchRange(addDays(to.value, 1), end)
		to.value = end
		await nextTick()
		if (el) el.scrollTop = el.scrollHeight - before // keep what the user looks at in place
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || __("Could not load later days")
	} finally {
		loadingLater.value = false
		sentinels.recheck()
	}
}

const sentinels = useScrollSentinels(scroller, topSentinel, bottomSentinel, { onTop: loadLater, onBottom: loadEarlier })

async function scrollToDate(date) {
	await nextTick()
	document.getElementById(`day-${date}`)?.scrollIntoView({ block: "start" })
	updateActiveDate()
}

async function start(center) {
	error.value = ""
	days.value = {}
	timeLogs.value = {}
	const start = addDays(center, -AROUND)
	const end = addDays(center, AROUND) < lastFuture.value ? addDays(center, AROUND) : lastFuture.value
	try {
		const first = await fetchRange(start, end)
		hasEarlier.value = first.has_earlier
		from.value = start
		to.value = end
		await scrollToDate(center)
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || __("Could not load your days")
	}
}

async function goTo(date) {
	if (date >= from.value && date <= to.value) return scrollToDate(date)
	router.replace({ name: "TodosPlan", params: date === today.value ? {} : { date } })
	await start(date)
}

let reloadTimer = null
function reloadAround(date) {
	clearTimeout(reloadTimer)
	reloadTimer = setTimeout(() => fetchRange(addDays(date, -1), addDays(date, 1)).catch(() => {}), 500)
}

useUserRealtime("cockpit_todos_changed", () => reloadAround(today.value))
useUserRealtime("cockpit_checkin_changed", () => reloadAround(today.value))
useUserRealtime("cockpit_timer_changed", () => reloadAround(today.value))

function onKeydown(event) {
	const tag = event.target?.tagName
	if (event.key !== "t" || event.ctrlKey || event.metaKey || event.altKey) return
	if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || event.target?.isContentEditable) return
	goTo(today.value)
}

watch(
	() => route.params.date,
	(date) => {
		if (date && (date < from.value || date > to.value)) start(date)
	}
)

onMounted(() => {
	start(route.params.date || today.value)
	ticker = setInterval(() => {
		now.value = new Date()
		today.value = todayIsoInUserTz()
	}, 60000)
	window.addEventListener("keydown", onKeydown)
	scroller.value?.addEventListener("scroll", onScroll, { passive: true })
})
onBeforeUnmount(() => {
	clearInterval(ticker)
	window.removeEventListener("keydown", onKeydown)
	scroller.value?.removeEventListener("scroll", onScroll)
	if (scrollFrame) cancelAnimationFrame(scrollFrame)
})
</script>
