<template>
	<!--
		Team Calendar (#1838): who is away when, as a timeline (one row per employee) or a month
		grid. The timeline scrolls sideways without end and opens on this week with at least four
		weeks ahead, for forecasting (PM, 2026-11-08); its day columns stretch to fill the width. Absences are neutral for every role: the API sends no leave type, so sick leave and
		annual leave look the same. Approved leave is green, a request blue and outlined, like the
		leave heatmap (#1836). Holidays carry the flag of their Holiday List's country.
	-->
	<div class="h-full min-h-0 overflow-y-auto bg-surface-gray-1 p-3 sm:p-5">
		<div class="flex w-full flex-col gap-4">
			<!--
				Coverage (PM, 2026-11-08): share of the team available, 100 % = everyone who should work
				is there. This week and the next three against the average of the last twelve months, so
				a thin week shows at a glance. A week card jumps the calendar to that week.
			-->
			<section v-if="coverage" class="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
				<div class="rounded-lg border border-outline-gray-2 bg-surface-white p-4" :title="__('Working days since {0}, approved leave only', [formatDate(coverage.average_from)])">
					<div class="text-xs font-medium uppercase tracking-wide text-ink-gray-5">{{ __("Ø coverage") }}</div>
					<div class="mt-2 text-2xl font-semibold tabular-nums text-ink-gray-9">{{ percent(coverage.average.coverage) }}</div>
					<div class="mt-1 text-xs text-ink-gray-6">{{ __("Last 12 months") }}</div>
				</div>
				<button
					v-for="(week, index) in coverage.weeks"
					:key="week.start"
					type="button"
					class="rounded-lg border border-outline-gray-2 bg-surface-white p-4 text-left hover:bg-surface-gray-1 focus:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3"
					:title="__('{0} of {1} person-days available, open requests counted as away', [formatCount(week.available), formatCount(week.expected)])"
					@click="goToDate(week.start)"
				>
					<div class="flex items-baseline justify-between gap-2">
						<span class="text-xs font-medium uppercase tracking-wide text-ink-gray-5">{{ weekName(index) }}</span>
						<span class="text-xs tabular-nums text-ink-gray-5">{{ shortRange(week.start, week.end) }}</span>
					</div>
					<div class="mt-2 flex items-baseline gap-2">
						<span class="text-2xl font-semibold tabular-nums text-ink-gray-9">{{ percent(week.coverage) }}</span>
						<span v-if="delta(week) !== null" :class="['text-xs font-medium tabular-nums', delta(week) < 0 ? 'text-ink-amber-3' : 'text-ink-green-3']">
							{{ delta(week) > 0 ? "+" : delta(week) < 0 ? "−" : "±" }}{{ formatCount(Math.abs(delta(week))) }} {{ __("pts") }}
						</span>
					</div>
					<!-- Bar: this week's coverage; the tick marks the average. -->
					<div class="relative mt-3 h-1.5 rounded-full bg-surface-gray-2">
						<div
							:class="['h-1.5 rounded-full', delta(week) !== null && delta(week) < 0 ? 'bg-[var(--ink-amber-3)]' : 'bg-surface-green-3']"
							:style="{ width: `${Math.max(0, Math.min(100, week.coverage ?? 0))}%` }"
						/>
						<div
							v-if="coverage.average.coverage !== null"
							class="absolute -top-1 h-3.5 w-0.5 bg-ink-gray-7"
							:style="{ left: `${coverage.average.coverage}%` }"
						/>
					</div>
				</button>
			</section>

			<section class="flex flex-wrap items-center gap-3 rounded-lg border border-outline-gray-2 bg-surface-white px-4 py-3">
				<div class="inline-flex rounded-md border border-outline-gray-2 p-0.5" role="group" :aria-label="__('View')">
					<button
						v-for="option in viewOptions"
						:key="option.value"
						type="button"
						:aria-pressed="view === option.value"
						:class="[
							'rounded px-3 py-1 text-sm transition-colors',
							view === option.value ? 'bg-surface-gray-7 text-ink-white' : 'text-ink-gray-7 hover:bg-surface-gray-2',
						]"
						@click="view = option.value"
					>
						{{ option.label }}
					</button>
				</div>
				<div class="flex items-center gap-1">
					<button type="button" :class="navButton" :aria-label="__('Four weeks back')" @click="step(-1)">
						<FeatherIcon name="chevron-left" class="h-4 w-4" />
					</button>
					<div class="min-w-36 text-center text-sm font-semibold capitalize text-ink-gray-9">{{ view === "timeline" ? visibleLabel : calendarLabel }}</div>
					<button type="button" :class="navButton" :aria-label="__('Four weeks ahead')" @click="step(1)">
						<FeatherIcon name="chevron-right" class="h-4 w-4" />
					</button>
					<button type="button" :class="[navButton, 'px-2 text-sm']" @click="goToday">{{ __("Today") }}</button>
				</div>
				<FormControl
					v-if="(data?.companies || []).length > 1"
					v-model="company"
					type="select"
					size="sm"
					:options="companyOptions"
					class="w-48"
				/>
				<span v-if="loading" class="text-xs text-ink-gray-5">{{ __("Loading…") }}</span>
				<div class="ml-auto flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-gray-6">
					<span class="inline-flex items-center gap-1.5"><span class="h-3 w-3 rounded-sm bg-surface-green-3" /> {{ __("Absent") }}</span>
					<span class="inline-flex items-center gap-1.5"><span class="h-3 w-3 rounded-sm border-2 border-dashed border-[color:var(--ink-blue-2)] bg-surface-blue-1" /> {{ __("Requested") }}</span>
					<span class="inline-flex items-center gap-1.5"><span class="h-3 w-3 rounded-sm" :style="halfStyle('--surface-green-3')" /> {{ __("Half day") }}</span>
					<span class="inline-flex items-center gap-1.5"><span class="h-3 w-3 rounded-sm bg-surface-amber-1" /> {{ __("Holiday") }}</span>
					<span class="inline-flex items-center gap-1.5">🎂 {{ __("Birthday") }}</span>
				</div>
			</section>

			<div v-if="loadError" class="rounded-lg border border-outline-gray-2 bg-surface-red-1 p-4 text-sm text-ink-red-4">
				{{ loadError }}
			</div>

			<!--
				Timeline: one row per employee, one column per day. Scrolling sideways loads more weeks at
				either end; the columns are as wide as fits this week and four more into the view.
			-->
			<section
				v-else-if="view === 'timeline'"
				ref="scroller"
				class="overflow-x-auto rounded-lg border border-outline-gray-2 bg-surface-white"
				@scroll.passive="onScroll"
			>
				<table class="table-fixed border-separate border-spacing-0 text-xs" :style="{ width: `${nameWidth + timelineDays.length * dayWidth}px` }">
					<colgroup>
						<col :style="{ width: `${nameWidth}px` }" />
						<col v-for="day in timelineDays" :key="day.iso" :style="{ width: `${dayWidth}px` }" />
					</colgroup>
					<thead>
						<tr>
							<th rowspan="2" class="sticky left-0 z-10 border-b border-r border-outline-gray-2 bg-surface-white px-3 py-2 text-left align-bottom font-medium text-ink-gray-5">
								<template v-if="!avatarsOnly">{{ __("Employee") }}</template>
							</th>
							<th
								v-for="span in monthSpans"
								:key="span.key"
								:colspan="span.days"
								class="border-b border-l border-outline-gray-2 px-2 py-1 text-left text-xs font-semibold capitalize text-ink-gray-8"
							>
								<span class="sticky" :style="{ left: `${nameWidth + 8}px` }">{{ span.label }}</span>
							</th>
						</tr>
						<tr>
							<th
								v-for="day in timelineDays"
								:key="day.iso"
								:class="[
									'border-b border-outline-gray-2 px-0 py-1 text-center font-medium',
									day.weekStart ? 'border-l' : '',
									day.iso === todayIso ? todayColumn : dayShade(day),
									day.weekend ? 'text-ink-gray-5' : 'text-ink-gray-6',
								]"
								:title="dayHeaderTitle(day)"
							>
								<!-- Today, for orientation: an amber column from the header down (PM, 2026-11-08). -->
								<div class="text-[10px] uppercase">{{ day.weekday }}</div>
								<div
									:class="[
										'mx-auto tabular-nums',
										day.iso === todayIso ? 'inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-[var(--ink-amber-3)] px-1 font-bold text-ink-white' : '',
									]"
								>
									{{ day.day }}
								</div>
								<div class="h-4 overflow-hidden leading-4">{{ day.flags.join("") }}</div>
							</th>
						</tr>
					</thead>
					<tbody>
						<tr v-if="!employees.length && !loading">
							<td :colspan="timelineDays.length + 1" class="px-4 py-8 text-left text-sm text-ink-gray-5">
								<span class="sticky left-4">{{ __("No active employees.") }}</span>
							</td>
						</tr>
						<tr v-for="row in timelineRows" :key="row.employee" class="group">
							<td class="sticky left-0 z-10 border-b border-r border-outline-gray-1 bg-surface-white px-2 py-1.5 group-hover:bg-surface-gray-1 sm:px-3">
								<div class="flex items-center gap-2" :title="row.employee_name">
									<Avatar size="sm" shape="circle" :image="row.image || undefined" :label="row.employee_name" />
									<span v-if="!avatarsOnly" class="truncate text-sm text-ink-gray-8">{{ row.employee_name }}</span>
								</div>
							</td>
							<td
								v-for="cell in row.cells"
								:key="cell.iso"
								:class="[
									'border-b border-outline-gray-1 p-0.5',
									cell.weekStart ? 'border-l border-l-outline-gray-2' : '',
									cell.today ? todayColumn : cell.holiday ? 'bg-surface-amber-1' : dayShade({ weekend: cell.off, altMonth: cell.altMonth }),
								]"
								:title="cell.title"
							>
								<div
									:class="['flex h-7 items-center justify-center rounded-sm', cell.classes]"
									:style="cell.style"
								>
									<span v-if="cell.birthday" class="text-sm leading-none">🎂</span>
									<span v-else-if="cell.flag && !cell.absence" class="text-[11px] leading-none">{{ cell.flag }}</span>
								</div>
							</td>
						</tr>
					</tbody>
				</table>
			</section>

			<!--
				Calendar: week rows that scroll up and down without end, like the timeline does sideways
				(PM, 2026-11-08). Opens with this week on top. Each week is a grid: day numbers, then
				holidays and birthdays, then one lane per absence. Consecutive days away are one bar
				(PM, 2026-11-09); a bar that runs on into the next or from the last week has a square end.
				Nobody is ever hidden: a week grows with the people away (PM, 2026-11-09).
			-->
			<section
				v-else
				ref="weekScroller"
				class="relative h-[calc(100vh-13rem)] min-h-96 overflow-y-auto rounded-lg [overflow-anchor:none] border border-outline-gray-2 bg-surface-white"
				@scroll.passive="onWeekScroll"
			>
				<div class="sticky top-0 z-20 grid grid-cols-7 border-b border-outline-gray-2 bg-surface-gray-1 text-center">
					<div v-for="label in weekdayLabels" :key="label" class="px-1 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-ink-gray-5">{{ label }}</div>
				</div>
				<div
					v-for="week in weeks"
					:key="week.key"
					:data-week="week.key"
					class="grid min-h-32 grid-cols-7"
					:style="{ gridTemplateRows: week.rows }"
				>
					<!-- Day backgrounds, over all rows of the week. -->
					<div
						v-for="(day, index) in week.days"
						:key="`bg-${day.iso}`"
						:style="{ gridColumn: index + 1, gridRow: '1 / -1' }"
						:class="[
							'border-b border-r border-outline-gray-1',
							day.iso === todayIso ? 'bg-surface-amber-1 ring-2 ring-inset ring-[var(--ink-amber-3)]' : dayShade(day),
							// Month boundary as a step line: left of the 1st, and above every day whose cell above is the old month.
							day.firstOfMonth ? 'border-l-2 border-l-outline-gray-4' : '',
							day.monthTop ? 'border-t-2 border-t-outline-gray-4' : '',
						]"
					/>
					<div
						v-for="(day, index) in week.days"
						:key="`d-${day.iso}`"
						:style="{ gridColumn: index + 1, gridRow: 1 }"
						class="relative flex min-w-0 items-center justify-between gap-1 px-1.5 pt-1.5"
					>
						<span
							:class="[
								'inline-flex h-6 min-w-6 items-center justify-center rounded-full px-1 text-xs tabular-nums',
								day.iso === todayIso ? 'bg-[var(--ink-amber-3)] font-bold text-ink-white' : 'text-ink-gray-6',
							]"
						>
							{{ day.day }}
						</span>
						<span v-if="day.firstOfMonth" class="truncate text-xs font-semibold capitalize text-ink-gray-9">{{ day.monthName }}</span>
					</div>
					<div
						v-for="(day, index) in week.days"
						:key="`x-${day.iso}`"
						:style="{ gridColumn: index + 1, gridRow: 2 }"
						class="relative flex min-w-0 flex-col gap-1 px-1.5 pt-1"
					>
						<div
							v-for="holiday in holidaysOn(day.iso)"
							:key="holiday.key"
							class="truncate rounded bg-surface-amber-1 px-1.5 py-0.5 text-[11px] text-ink-amber-3"
							:title="holiday.title"
						>
							{{ holiday.flag }} {{ holiday.description }}
						</div>
						<div
							v-for="birthday in birthdaysOn(day.iso)"
							:key="`b-${birthday.employee}`"
							class="flex items-center gap-1 truncate rounded bg-surface-gray-2 px-1.5 py-0.5 text-[11px] text-ink-gray-8"
							:title="__('Birthday: {0}', [birthday.name])"
						>
							<span>🎂</span><span class="truncate">{{ birthday.name }}</span>
						</div>
					</div>
					<div
						v-for="bar in week.bars"
						:key="bar.key"
						:style="{ gridColumn: `${bar.start + 1} / span ${bar.span}`, gridRow: 3 + bar.lane }"
						:class="[
							'relative mt-1 flex min-w-0 items-center gap-1 overflow-hidden px-1 text-[11px]',
							bar.requested
								? 'border border-dashed border-[color:var(--ink-blue-2)] bg-surface-blue-1 text-ink-blue-3'
								: 'bg-surface-green-2 text-ink-green-3',
							bar.continuesBefore ? 'ml-0 rounded-l-none border-l-0' : 'ml-1.5 rounded-l',
							bar.continuesAfter ? 'mr-0 rounded-r-none border-r-0' : 'mr-1.5 rounded-r',
						]"
						:title="bar.title"
					>
						<Avatar size="xs" shape="circle" :image="bar.image || undefined" :label="bar.name" />
						<span class="truncate">{{ bar.name }}</span>
						<span v-if="bar.half" class="shrink-0 opacity-75">½</span>
					</div>
				</div>
			</section>
		</div>
	</div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onBeforeUpdate, onUpdated, ref, watch } from "vue"
import { Avatar, FeatherIcon, FormControl, call } from "frappe-ui"
import { formatDate, getFirstDayOfWeekIndex, userLocale } from "@spa/utils/datetime.js"
import { __ } from "@spa/utils/i18n.js"
import { errorMessage } from "@spa/contracts/contractFormat.js"

const API = "phamos.api.hr_team_calendar.get_team_calendar"
const VIEW_KEY = "phamos-hr-team-calendar-view"

/**
 * Background of a day (PM, 2026-11-08): weekends one darker gray, other days alternate white and
 * light gray by month, so a new month shows without reading the dates.
 */
function dayShade(day) {
	if (day.weekend) return "bg-surface-gray-2"
	return day.altMonth ? "bg-surface-gray-1" : "bg-surface-white"
}

// Today's column in the timeline: amber edges and a light amber fill over every row.
const todayColumn = "border-x-2 border-x-[color:var(--ink-amber-3)] bg-surface-amber-1"

const navButton =
	"inline-flex h-7 items-center justify-center rounded-md px-1.5 text-ink-gray-7 hover:bg-surface-gray-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3"
const viewOptions = [
	{ value: "timeline", label: __("Timeline") },
	{ value: "month", label: __("Calendar") },
]

function readView() {
	try {
		return localStorage.getItem(VIEW_KEY) === "month" ? "month" : "timeline"
	} catch {
		return "timeline"
	}
}
const view = ref(readView())
watch(view, (value) => {
	try {
		localStorage.setItem(VIEW_KEY, value)
	} catch {
		// private window: the toggle still works, it is just not remembered
	}
})

const now = new Date()
const company = ref("")
const data = ref(null)
const loading = ref(false)
const loadError = ref("")

function iso(date) {
	return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`
}
function addDays(date, days) {
	return new Date(date.getFullYear(), date.getMonth(), date.getDate() + days)
}
function parse(value) {
	const [y, m, d] = String(value).slice(0, 10).split("-").map(Number)
	return new Date(y, m - 1, d)
}
const todayIso = iso(now)

/** A country's flag from its two-letter code: regional indicator letters. */
function flagOf(code) {
	if (!code || !/^[A-Z]{2}$/.test(code)) return ""
	return String.fromCodePoint(...[...code].map((c) => 0x1f1e6 + c.charCodeAt(0) - 65))
}
function halfStyle(fill) {
	return { background: `linear-gradient(135deg, var(${fill}) 50%, transparent 50%)` }
}

const weekdayFormat = computed(() => new Intl.DateTimeFormat(userLocale(), { weekday: "short" }))
const monthYearFormat = computed(() => new Intl.DateTimeFormat(userLocale(), { month: "long", year: "numeric" }))

// ---- Timeline range: continuous days, extended in chunks while scrolling ----
const WEEK = 7
const CHUNK_DAYS = 8 * WEEK // added at an end when the scroll comes near it
const MAX_RANGE_DAYS = 52 * WEEK // the API allows 400; the far end is dropped beyond this
const VISIBLE_DAYS = 5 * WEEK // this week and four ahead fill the view on a wide screen
const MIN_DAY_WIDTH = 22

function weekStartOf(date) {
	return addDays(date, -((date.getDay() - getFirstDayOfWeekIndex() + 7) % 7))
}
const thisWeek = weekStartOf(now)
// Two weeks back for context, then this week and enough ahead to scroll into.
const timelineStart = ref(addDays(thisWeek, -2 * WEEK))
const timelineEnd = ref(addDays(thisWeek, 14 * WEEK - 1))

// Two days before this week, so today's column never hides behind the names; with five weeks
// across, the four weeks ahead stay in view.
const viewStart = addDays(thisWeek, -2)

// ---- Calendar range: week rows, extended in chunks while scrolling up or down ----
const weeksStart = ref(addDays(thisWeek, -2 * WEEK))
const weeksEnd = ref(addDays(thisWeek, 12 * WEEK - 1))
const weekScroller = ref(null)
const topWeekKey = ref(iso(thisWeek)) // the week at the top of the view

function weekElement(key) {
	return weekScroller.value?.querySelector(`[data-week="${key}"]`) || null
}
function headerHeight() {
	return weekScroller.value?.firstElementChild?.offsetHeight || 0
}
function scrollToWeek(date, behavior = "smooth") {
	const key = iso(weekStartOf(date))
	const element = weekElement(key)
	if (!element) return
	topWeekKey.value = key
	weekScroller.value.scrollTo({ top: Math.max(0, element.offsetTop - headerHeight()), behavior })
}
watch(weekScroller, (element, previous) => {
	// Opening the calendar: this week on top, the weeks ahead below.
	if (element && !previous) nextTick(() => scrollToWeek(thisWeek, "auto"))
})

/** The first week whose lower edge is below the sticky header. */
function findTopWeek() {
	const element = weekScroller.value
	if (!element) return null
	const line = element.scrollTop + headerHeight()
	for (const row of element.querySelectorAll("[data-week]")) {
		if (row.offsetTop + row.offsetHeight > line) return row.dataset.week
	}
	return null
}

let extendingWeeks = false
function onWeekScroll() {
	const element = weekScroller.value
	if (!element) return
	topWeekKey.value = findTopWeek() || topWeekKey.value
	if (extendingWeeks) return
	const margin = 400
	if (element.scrollTop + element.clientHeight > element.scrollHeight - margin) extendWeeks(1)
	else if (element.scrollTop < margin) extendWeeks(-1)
}

/** Add eight weeks at one end; past a year, drop weeks at the other end. */
async function extendWeeks(direction) {
	extendingWeeks = true
	const tooLong = () => Math.round((weeksEnd.value - weeksStart.value) / 86400000) >= MAX_RANGE_DAYS
	if (direction > 0) {
		weeksEnd.value = addDays(weeksEnd.value, CHUNK_DAYS)
		if (tooLong()) weeksStart.value = addDays(weeksStart.value, CHUNK_DAYS)
	} else {
		weeksStart.value = addDays(weeksStart.value, -CHUNK_DAYS)
		if (tooLong()) weeksEnd.value = addDays(weeksEnd.value, -CHUNK_DAYS)
	}
	await nextTick()
	extendingWeeks = false
}

// Weeks change height when weeks are added above or their leave arrives. Browser scroll anchoring
// is off for this list ([overflow-anchor:none]); instead the top week keeps its place on screen
// across every re-render.
let anchor = null
onBeforeUpdate(() => {
	anchor = null
	const element = weekElement(topWeekKey.value)
	if (view.value === "month" && element) anchor = { key: topWeekKey.value, offset: element.offsetTop - weekScroller.value.scrollTop }
})
onUpdated(() => {
	const element = anchor && weekElement(anchor.key)
	if (!element) return
	const top = element.offsetTop - anchor.offset
	if (Math.abs(weekScroller.value.scrollTop - top) > 1) weekScroller.value.scrollTop = top
})

/** One week: its days, and the absence bars laid out in lanes so each run of days is one bar. */
function buildWeek(start) {
	const days = Array.from({ length: WEEK }, (_, index) => {
		const date = addDays(start, index)
		return {
			iso: iso(date),
			day: date.getDate(),
			weekend: [0, 6].includes(date.getDay()),
			altMonth: date.getMonth() % 2 === 1,
			firstOfMonth: date.getDate() === 1,
			monthTop: addDays(date, -WEEK).getMonth() !== date.getMonth(),
			monthName: date.toLocaleDateString(userLocale(), { month: "long" }),
		}
	})
	const before = iso(addDays(start, -1))
	const after = iso(addDays(start, WEEK))
	const segments = []
	for (const employee of employees.value) {
		const away = absenceDays.value[employee.employee]
		if (!away) continue
		let segment = null
		days.forEach((day, index) => {
			const absence = away[day.iso]
			if (!absence) {
				segment = null
			} else if (segment && segment.requested === absence.requested) {
				segment.end = index
				segment.half ||= absence.half
			} else {
				segment = { employee, requested: absence.requested, start: index, end: index, half: absence.half }
				segments.push(segment)
			}
		})
		for (const item of segments.filter((s) => s.employee === employee)) {
			item.continuesBefore = item.start === 0 && away[before]?.requested === item.requested
			item.continuesAfter = item.end === WEEK - 1 && away[after]?.requested === item.requested
		}
	}
	// Longest first at the same start, then the first free lane.
	segments.sort((a, b) => a.start - b.start || b.end - a.end)
	const laneEnds = []
	for (const segment of segments) {
		let lane = laneEnds.findIndex((end) => end < segment.start)
		if (lane === -1) lane = laneEnds.push(-1) - 1
		laneEnds[lane] = segment.end
		segment.lane = lane
	}
	// The last row takes the spare height of a short week, so the bars sit right under the dates.
	const rows = ["auto", "auto", ...Array(laneEnds.length).fill("1.375rem"), "minmax(0.375rem, 1fr)"].join(" ")
	return {
		key: iso(start),
		days,
		rows,
		bars: segments.map((s) => ({
				key: `${s.employee.employee}-${s.start}`,
				start: s.start,
				span: s.end - s.start + 1,
				lane: s.lane,
				requested: s.requested,
				half: s.half,
				continuesBefore: s.continuesBefore,
				continuesAfter: s.continuesAfter,
				name: s.employee.employee_name,
				image: s.employee.image,
				title: [
					s.employee.employee_name,
					`${formatDate(days[s.start].iso)} – ${formatDate(days[s.end].iso)}`,
					s.requested ? __("Absent (requested)") : __("Absent"),
					s.half ? __("Half day") : "",
				]
					.filter(Boolean)
					.join(" · "),
			})),
	}
}
const weeks = computed(() => {
	const result = []
	for (let start = weeksStart.value; start <= weeksEnd.value; start = addDays(start, WEEK)) result.push(buildWeek(start))
	return result
})

const weekdayLabels = computed(() =>
	Array.from({ length: 7 }, (_, i) => weekdayFormat.value.format(addDays(weeksStart.value, i))),
)
/** The month of the top week in view (its last day, so a week into a new month counts there). */
const calendarLabel = computed(() => monthYearFormat.value.format(addDays(parse(topWeekKey.value), WEEK - 1)))

const scroller = ref(null)
const viewWidth = ref(0)
const scrollLeft = ref(0)
// Narrow screens: a shorter name column, on a phone avatars only (name in the tooltip), so days fit.
const avatarsOnly = computed(() => Boolean(viewWidth.value) && viewWidth.value < 480)
const nameWidth = computed(() => {
	if (avatarsOnly.value) return 48
	return viewWidth.value && viewWidth.value < 640 ? 140 : 208
})
const dayWidth = computed(() => Math.max(MIN_DAY_WIDTH, Math.floor((viewWidth.value - nameWidth.value) / VISIBLE_DAYS) || MIN_DAY_WIDTH))

let resizeObserver = null
watch(scroller, (element, previous) => {
	resizeObserver?.disconnect()
	if (!element) return
	resizeObserver = new ResizeObserver(() => (viewWidth.value = element.clientWidth))
	resizeObserver.observe(element)
	viewWidth.value = element.clientWidth
	// Opening the timeline: at this week.
	if (!previous) nextTick(() => scrollToDate(viewStart, "auto"))
})
onBeforeUnmount(() => resizeObserver?.disconnect())

function dayIndex(date) {
	return Math.round((date - timelineStart.value) / 86400000)
}
function scrollToDate(date, behavior = "smooth") {
	scroller.value?.scrollTo({ left: Math.max(0, dayIndex(date) * dayWidth.value), behavior })
}

let extending = false
function onScroll() {
	const element = scroller.value
	if (!element || extending) return
	scrollLeft.value = element.scrollLeft
	const margin = 2 * WEEK * dayWidth.value
	if (element.scrollLeft + element.clientWidth > element.scrollWidth - margin) extend(1)
	else if (element.scrollLeft < margin) extend(-1)
}

/** Add a chunk of days at one end; past the maximum, drop days at the other end. */
async function extend(direction) {
	extending = true
	let shift = 0 // days added (+) or dropped (-) at the start, to keep the view where it was
	if (direction > 0) {
		timelineEnd.value = addDays(timelineEnd.value, CHUNK_DAYS)
		if (dayIndex(timelineEnd.value) >= MAX_RANGE_DAYS) {
			timelineStart.value = addDays(timelineStart.value, CHUNK_DAYS)
			shift = -CHUNK_DAYS
		}
	} else {
		timelineStart.value = addDays(timelineStart.value, -CHUNK_DAYS)
		shift = CHUNK_DAYS
		if (dayIndex(timelineEnd.value) >= MAX_RANGE_DAYS) timelineEnd.value = addDays(timelineEnd.value, -CHUNK_DAYS)
	}
	await nextTick()
	if (shift && scroller.value) scroller.value.scrollLeft += shift * dayWidth.value
	scrollLeft.value = scroller.value?.scrollLeft || 0
	extending = false
}

const timelineDays = computed(() => {
	const days = []
	for (let date = timelineStart.value; date <= timelineEnd.value; date = addDays(date, 1)) {
		const key = iso(date)
		days.push({
			iso: key,
			date,
			day: date.getDate(),
			weekday: weekdayFormat.value.format(date).slice(0, 2),
			weekend: [0, 6].includes(date.getDay()),
			altMonth: date.getMonth() % 2 === 1,
			weekStart: date.getDay() === getFirstDayOfWeekIndex(),
			flags: [...new Set(holidaysOn(key).map((h) => h.flag).filter(Boolean))],
		})
	}
	return days
})

/** One header cell per month over its days. */
const monthSpans = computed(() => {
	const spans = []
	for (const day of timelineDays.value) {
		const key = `${day.date.getFullYear()}-${day.date.getMonth()}`
		const last = spans[spans.length - 1]
		if (last?.key === key) last.days++
		else spans.push({ key, days: 1, label: day.date.toLocaleDateString(userLocale(), { month: "long", year: "numeric" }) })
	}
	return spans
})

/** The month at the left edge of the view, for the toolbar. */
const visibleLabel = computed(() => {
	const days = timelineDays.value
	const first = days[Math.min(days.length - 1, Math.max(0, Math.floor(scrollLeft.value / dayWidth.value)))]
	return first ? monthYearFormat.value.format(first.date) : ""
})

// ---- Coverage cards ----
const coverage = ref(null)
let coverageRequest = 0
async function loadCoverage() {
	const id = ++coverageRequest
	try {
		const result = await call("phamos.api.hr_team_calendar.get_coverage", { company: company.value || null })
		if (id === coverageRequest) coverage.value = result
	} catch {
		// The cards are extra; the calendar still works without them.
		if (id === coverageRequest) coverage.value = null
	}
}
watch(company, loadCoverage, { immediate: true })

const numberFormat = computed(() => new Intl.NumberFormat(userLocale(), { maximumFractionDigits: 1 }))
function formatCount(value) {
	return numberFormat.value.format(value ?? 0)
}
function percent(value) {
	return value === null || value === undefined ? "—" : `${formatCount(value)} %`
}
/** Points above (+) or below (−) the average, to one decimal; null without both values. */
function delta(week) {
	const average = coverage.value?.average?.coverage
	if (week.coverage === null || average === null || average === undefined) return null
	return Math.round((week.coverage - average) * 10) / 10
}
function weekName(index) {
	if (index === 0) return __("This week")
	if (index === 1) return __("Next week")
	return __("In {0} weeks", [index])
}
function shortRange(start, end) {
	const format = new Intl.DateTimeFormat(userLocale(), { day: "numeric", month: "short" })
	return `${format.format(parse(start))} – ${format.format(parse(end))}`
}
function goToDate(value) {
	const date = parse(value)
	if (view.value === "timeline") scrollToDate(addDays(date, -2))
	else scrollToWeek(date)
}

// ---- Loading ----
const range = computed(() =>
	view.value === "timeline"
		? { from: timelineStart.value, to: timelineEnd.value }
		: { from: weeksStart.value, to: weeksEnd.value },
)

// Paging or scrolling quickly: only the newest request may fill the page.
let requestId = 0
async function load() {
	const id = ++requestId
	loading.value = true
	loadError.value = ""
	try {
		const result = await call(API, {
			from_date: iso(range.value.from),
			to_date: iso(range.value.to),
			company: company.value || null,
		})
		if (id === requestId) data.value = result
	} catch (error) {
		if (id === requestId) loadError.value = errorMessage(error) || __("The team calendar could not be loaded.")
	} finally {
		if (id === requestId) loading.value = false
	}
}
watch(() => [iso(range.value.from), iso(range.value.to), company.value], load, { immediate: true })

/** ‹ and ›: four weeks, sideways in the timeline, up or down in the calendar. */
function step(direction) {
	if (view.value === "timeline") scroller.value?.scrollBy({ left: direction * 4 * WEEK * dayWidth.value, behavior: "smooth" })
	else scrollToWeek(addDays(parse(topWeekKey.value), direction * 4 * WEEK))
}
function goToday() {
	if (view.value === "timeline") scrollToDate(viewStart)
	else scrollToWeek(thisWeek)
}

const companyOptions = computed(() => [
	{ label: __("All companies"), value: "" },
	...(data.value?.companies || []).map((name) => ({ label: name, value: name })),
])
const employees = computed(() => data.value?.employees || [])
const employeeByName = computed(() => Object.fromEntries(employees.value.map((e) => [e.employee, e])))
const holidayLists = computed(() => data.value?.holiday_lists || {})

/** employee → { date → absence } for every day an absence covers. */
const absenceDays = computed(() => {
	const map = {}
	for (const absence of data.value?.absences || []) {
		const days = (map[absence.employee] ||= {})
		const half = absence.half_day ? String(absence.half_day_date || absence.from_date).slice(0, 10) : null
		const end = parse(absence.to_date)
		for (let date = parse(absence.from_date); date <= end; date = addDays(date, 1)) {
			const key = iso(date)
			// Approved wins over a request on the same day.
			if (days[key] && !days[key].requested) continue
			days[key] = { requested: absence.requested, half: half === key }
		}
	}
	return map
})

/** holiday list → { date → holiday } and → Set(weekly off dates). */
const holidaysByList = computed(() => {
	const result = {}
	for (const [name, list] of Object.entries(holidayLists.value)) {
		result[name] = {
			flag: flagOf(list.country_code),
			country: list.country,
			holidays: Object.fromEntries(list.holidays.map((h) => [String(h.date).slice(0, 10), h])),
			weeklyOffs: new Set(list.weekly_offs.map((d) => String(d).slice(0, 10))),
			hasWeeklyOffs: list.weekly_offs.length > 0,
		}
	}
	return result
})

const birthdaysByDate = computed(() => {
	const map = {}
	for (const birthday of data.value?.birthdays || []) {
		const key = String(birthday.date).slice(0, 10)
		const employee = employeeByName.value[birthday.employee]
		;(map[key] ||= []).push({ employee: birthday.employee, name: employee?.employee_name || birthday.employee })
	}
	return map
})


/** Holidays on a date, one chip per holiday and country, with the employees it applies to. */
function holidaysOn(date) {
	const chips = {}
	for (const employee of employees.value) {
		const list = holidaysByList.value[employee.holiday_list]
		const holiday = list?.holidays[date]
		if (!holiday) continue
		const key = `${list.flag}|${holiday.description}`
		const chip = (chips[key] ||= { key, flag: list.flag, description: holiday.description, country: list.country, names: [] })
		chip.names.push(employee.employee_name)
	}
	return Object.values(chips).map((chip) => ({
		...chip,
		title: `${chip.description}${chip.country ? ` (${chip.country})` : ""}: ${chip.names.join(", ")}`,
	}))
}
function birthdaysOn(date) {
	return birthdaysByDate.value[date] || []
}

function dayHeaderTitle(day) {
	const holidays = holidaysOn(day.iso)
	return [formatDate(day.iso), ...holidays.map((h) => `${h.flag} ${h.title}`)].join("\n")
}

const timelineRows = computed(() =>
	employees.value.map((employee) => ({ ...employee, cells: timelineDays.value.map((day) => cellFor(employee, day)) })),
)

/** What one timeline cell shows for an employee on a day. */
function cellFor(employee, day) {
	const list = holidaysByList.value[employee.holiday_list]
	const holiday = list?.holidays[day.iso]
	// The employee's own weekly offs where the list has them, else Saturday and Sunday.
	const off = list?.hasWeeklyOffs ? list.weeklyOffs.has(day.iso) : day.weekend
	const absence = absenceDays.value[employee.employee]?.[day.iso]
	const birthday = birthdaysOn(day.iso).some((b) => b.employee === employee.employee)
	const parts = [formatDate(day.iso)]
	if (holiday) parts.push(`${list.flag} ${holiday.description}`)
	if (absence) parts.push(absence.requested ? __("Absent (requested)") : __("Absent"))
	if (absence?.half) parts.push(__("Half day"))
	if (birthday) parts.push(`🎂 ${__("Birthday")}`)
	let classes = ""
	let style = null
	if (absence) {
		const fill = absence.requested ? "--surface-blue-2" : "--surface-green-3"
		if (absence.half) style = halfStyle(fill)
		else classes = absence.requested ? "border-2 border-dashed border-[color:var(--ink-blue-2)] bg-surface-blue-1" : "bg-surface-green-3"
		if (absence.half && absence.requested) classes = "border-2 border-dashed border-[color:var(--ink-blue-2)]"
	}
	return {
		iso: day.iso,
		altMonth: day.altMonth,
		weekStart: day.weekStart,
		today: day.iso === todayIso,
		absence: Boolean(absence),
		holiday: Boolean(holiday),
		flag: holiday ? list.flag : "",
		off,
		birthday,
		classes,
		style,
		title: `${employee.employee_name}\n${parts.join(" · ")}`,
	}
}
</script>
