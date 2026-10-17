<template>
	<div class="h-full min-h-0 overflow-y-auto bg-surface-gray-1 p-5">
		<div class="mx-auto flex max-w-7xl flex-col gap-5">
			<div class="flex flex-wrap items-center justify-between gap-3">
				<p class="text-sm text-ink-gray-6" aria-live="polite">{{ headline }}</p>
				<div class="flex items-center gap-2">
					<TabButtons v-model="period" :buttons="PERIOD_BUTTONS" />
				</div>
			</div>

			<div v-if="error" class="rounded-lg border border-outline-gray-2 bg-surface-red-1 p-4 text-sm text-ink-red-4">
				{{ error }}
			</div>
			<div v-else-if="!data" class="flex min-h-64 items-center justify-center text-sm text-ink-gray-5">Loading…</div>
			<div v-else-if="!data.state.employee" class="rounded-lg border border-outline-gray-2 bg-surface-white p-5 text-sm text-ink-gray-6">
				Check-ins need an active Employee linked to your user. Please ask HR.
			</div>
			<template v-else>
				<section class="grid grid-cols-2 gap-3 xl:grid-cols-4">
					<StatCard label="Today" :value="formatWorked(todayMinutes)" :hint="todayHint" />
					<StatCard
						:label="`Last ${period} days`"
						:value="formatWorked(totals.worked_minutes)"
						:hint="`${totals.days_worked} days · this week ${formatWorked(totals.week_minutes)}`"
					/>
					<StatCard label="Average day" :value="totals.average_minutes == null ? '—' : formatWorked(totals.average_minutes)" hint="on days with check-ins" />
					<StatCard label="Typical day" :value="typicalDay" hint="average first check-in and last check-out" />
				</section>

				<PeriodBars
					title="Worked time"
					:subtitle="period === 90 ? 'Hours per week, from check-in to check-out' : 'Hours per day, from check-in to check-out'"
					:periods="bars"
					:series="[{ label: 'Hours' }]"
				/>

				<section v-if="totals.missing_out.length" class="rounded-lg border border-outline-gray-2 bg-surface-white p-5">
					<h2 class="text-base font-semibold text-ink-gray-9">Days without a check-out</h2>
					<p class="mb-3 text-sm text-ink-gray-5">These days do not count as worked time. HR can add the missing check-out.</p>
					<ul class="divide-y divide-outline-gray-1 text-sm">
						<li v-for="day in totals.missing_out" :key="day.date" class="flex items-center justify-between py-2">
							<span class="text-ink-gray-8">{{ dayLabel(day.date) }}</span>
							<span class="text-ink-gray-5">checked in {{ shortTime(day.first_in) }}</span>
						</li>
					</ul>
				</section>
			</template>
		</div>
	</div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { call, TabButtons } from "frappe-ui"
import PeriodBars from "@spa/components/dashboard/PeriodBars.vue"
import StatCard from "@spa/components/dashboard/StatCard.vue"
import { useUserRealtime } from "@spa/composables/useUserRealtime.js"
import { caption, formatWorked, liveWorkedMinutes } from "@spa/utils/checkinSummary.js"
import { formatDate, formatTime } from "@spa/utils/datetime.js"
import spaConfig from "@/config"

const PERIOD_KEY = "personal-checkins-period"
const PERIOD_BUTTONS = [7, 30, 90].map((value) => ({ label: `${value} days`, value }))

const data = ref(null)
const error = ref("")
const period = ref(readPeriod())
const loadedAt = ref(Date.now())
const tick = ref(Date.now())
let ticker = null

const shortTime = (value) => (value ? formatTime(value).slice(0, 5) : "—")
const totals = computed(() => data.value?.totals || {})
const todayMinutes = computed(() => liveWorkedMinutes(data.value?.state, (tick.value - loadedAt.value) / 1000))
const todayHint = computed(() => caption(data.value?.state, shortTime, (v) => formatDate(String(v).slice(0, 10))))
const headline = computed(() => {
	const state = data.value?.state
	if (!state?.employee) return "Your check-ins and worked time."
	return state.next_action === "OUT" ? `Checked in, ${caption(state, shortTime, (v) => formatDate(String(v).slice(0, 10)))}.` : "Checked out."
})
const typicalDay = computed(() => {
	const { average_start: start, average_end: end } = totals.value
	if (start == null) return "—"
	const hm = (m) => `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`
	return end == null ? `${hm(start)} –` : `${hm(start)} – ${hm(end)}`
})
const bars = computed(() => {
	const days = data.value?.days || []
	const byDate = Object.fromEntries(days.map((d) => [String(d.date), d.worked_minutes]))
	const rows = []
	const today = new Date()
	for (let i = period.value - 1; i >= 0; i--) {
		const d = new Date(today.getFullYear(), today.getMonth(), today.getDate() - i)
		const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
		rows.push({ date: d, minutes: byDate[key] || 0 })
	}
	if (period.value !== 90) {
		// 30 bars only have room for the day of the month.
		const label = (d) => (period.value === 7 ? d.toLocaleDateString([], { weekday: "short", day: "numeric" }) : String(d.getDate()))
		return rows.map((r) => ({ label: label(r.date), values: [round1(r.minutes / 60)] }))
	}
	const weeks = []
	for (const r of rows) {
		const monday = new Date(r.date.getFullYear(), r.date.getMonth(), r.date.getDate() - ((r.date.getDay() + 6) % 7))
		const label = monday.toLocaleDateString([], { day: "numeric", month: "short" })
		if (!weeks.length || weeks[weeks.length - 1].label !== label) weeks.push({ label, minutes: 0 })
		weeks[weeks.length - 1].minutes += r.minutes
	}
	return weeks.map((w) => ({ label: w.label, values: [round1(w.minutes / 60)] }))
})

function round1(value) {
	return Math.round(value * 10) / 10
}

function dayLabel(value) {
	const d = new Date(`${String(value).slice(0, 10)}T12:00:00`)
	return `${d.toLocaleDateString([], { weekday: "long" })} ${formatDate(String(value).slice(0, 10))}`
}

function readPeriod() {
	try {
		const stored = Number(localStorage.getItem(PERIOD_KEY))
		return [7, 30, 90].includes(stored) ? stored : 30
	} catch {
		return 30
	}
}

async function load() {
	try {
		data.value = await call(`${spaConfig.api}.get_checkin_dashboard`, { period: period.value })
		loadedAt.value = Date.now()
		error.value = ""
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not load your check-ins"
	}
}

watch(period, (value) => {
	try {
		localStorage.setItem(PERIOD_KEY, String(value))
	} catch {
		/* private mode */
	}
	load()
})
useUserRealtime("cockpit_checkin_changed", load)
onMounted(() => {
	load()
	ticker = setInterval(() => (tick.value = Date.now()), 30000)
})
onBeforeUnmount(() => clearInterval(ticker))
</script>
