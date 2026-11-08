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
					<button type="button" :class="navButton" :aria-label="view === 'timeline' ? __('Four weeks back') : __('Previous month')" @click="step(-1)">
						<FeatherIcon name="chevron-left" class="h-4 w-4" />
					</button>
					<div class="min-w-36 text-center text-sm font-semibold capitalize text-ink-gray-9">{{ view === "timeline" ? visibleLabel : monthLabel }}</div>
					<button type="button" :class="navButton" :aria-label="view === 'timeline' ? __('Four weeks ahead') : __('Next month')" @click="step(1)">
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
									day.weekend ? 'bg-surface-gray-2 text-ink-gray-5' : 'text-ink-gray-6',
									day.iso === todayIso ? 'bg-surface-amber-1 text-ink-amber-3' : '',
								]"
								:title="dayHeaderTitle(day)"
							>
								<div class="text-[10px] uppercase">{{ day.weekday }}</div>
								<div :class="['tabular-nums', day.iso === todayIso ? 'font-bold' : '']">{{ day.day }}</div>
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
									cell.holiday ? 'bg-surface-amber-1' : cell.off ? 'bg-surface-gray-2' : '',
								]"
								:title="cell.title"
							>
								<div
									:class="['flex h-7 items-center justify-center rounded-sm', cell.classes, cell.today && !cell.absence ? 'ring-1 ring-inset ring-[var(--ink-amber-3)]' : '']"
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

			<!-- Month grid: day cells with holidays, birthdays and absences as chips. -->
			<section v-else class="overflow-hidden rounded-lg border border-outline-gray-2 bg-surface-white">
				<div class="grid grid-cols-7 border-b border-outline-gray-2 bg-surface-gray-1 text-center">
					<div v-for="label in weekdayLabels" :key="label" class="px-1 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-ink-gray-5">{{ label }}</div>
				</div>
				<div class="grid grid-cols-7">
					<div
						v-for="day in gridDays"
						:key="day.iso"
						:class="[
							'min-h-32 border-b border-r border-outline-gray-1 p-1.5',
							day.inMonth ? (day.weekend ? 'bg-surface-gray-1' : 'bg-surface-white') : 'bg-surface-gray-1 opacity-60',
						]"
					>
						<div class="mb-1 flex items-center justify-between">
							<span
								:class="[
									'inline-flex h-6 min-w-6 items-center justify-center rounded-full px-1 text-xs tabular-nums',
									day.iso === todayIso ? 'bg-surface-amber-2 font-bold text-ink-amber-3' : 'text-ink-gray-6',
								]"
							>
								{{ day.day }}
							</span>
						</div>
						<div class="flex flex-col gap-1">
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
							<div
								v-for="absence in absencesOn(day.iso).slice(0, MAX_CHIPS)"
								:key="`a-${absence.employee}`"
								:class="[
									'flex items-center gap-1 truncate rounded px-1 py-0.5 text-[11px]',
									absence.requested
										? 'border border-dashed border-[color:var(--ink-blue-2)] bg-surface-blue-1 text-ink-blue-3'
										: 'bg-surface-green-2 text-ink-green-3',
								]"
								:title="absence.title"
							>
								<Avatar size="xs" shape="circle" :image="absence.image || undefined" :label="absence.name" />
								<span class="truncate">{{ absence.name }}</span>
								<span v-if="absence.half" class="shrink-0 opacity-75">½</span>
							</div>
							<div v-if="absencesOn(day.iso).length > MAX_CHIPS" class="px-1 text-[11px] text-ink-gray-5" :title="absencesOn(day.iso).slice(MAX_CHIPS).map((a) => a.name).join(', ')">
								{{ __("+{0} more", [absencesOn(day.iso).length - MAX_CHIPS]) }}
							</div>
						</div>
					</div>
				</div>
			</section>
		</div>
	</div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue"
import { Avatar, FeatherIcon, FormControl, call } from "frappe-ui"
import { formatDate, getFirstDayOfWeekIndex, userLocale } from "@spa/utils/datetime.js"
import { __ } from "@spa/utils/i18n.js"
import { errorMessage } from "@spa/contracts/contractFormat.js"

const API = "phamos.api.hr_team_calendar.get_team_calendar"
const MAX_CHIPS = 4
const VIEW_KEY = "phamos-hr-team-calendar-view"

const navButton =
	"inline-flex h-7 items-center justify-center rounded-md px-1.5 text-ink-gray-7 hover:bg-surface-gray-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3"
const viewOptions = [
	{ value: "timeline", label: __("Timeline") },
	{ value: "month", label: __("Month") },
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
const month = ref(new Date(now.getFullYear(), now.getMonth(), 1))
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

const monthLabel = computed(() => month.value.toLocaleDateString(userLocale(), { month: "long", year: "numeric" }))
const weekdayFormat = computed(() => new Intl.DateTimeFormat(userLocale(), { weekday: "short" }))

// Month grid: whole weeks around the month, starting on the system's first day of the week.
const gridStart = computed(() => {
	const first = month.value
	const offset = (first.getDay() - getFirstDayOfWeekIndex() + 7) % 7
	return addDays(first, -offset)
})
const gridEnd = computed(() => {
	const last = new Date(month.value.getFullYear(), month.value.getMonth() + 1, 0)
	const offset = (getFirstDayOfWeekIndex() + 6 - last.getDay() + 7) % 7
	return addDays(last, offset)
})
const weekdayLabels = computed(() =>
	Array.from({ length: 7 }, (_, i) => weekdayFormat.value.format(addDays(gridStart.value, i))),
)

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
	// Opening the timeline: start at this week.
	if (!previous) nextTick(() => scrollToDate(thisWeek, "auto"))
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
	return first ? first.date.toLocaleDateString(userLocale(), { month: "long", year: "numeric" }) : ""
})

// ---- Loading ----
const range = computed(() =>
	view.value === "timeline"
		? { from: timelineStart.value, to: timelineEnd.value }
		: { from: gridStart.value, to: gridEnd.value },
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

/** ‹ and ›: a month in the month grid, four weeks in the timeline. */
function step(direction) {
	if (view.value === "timeline") {
		scroller.value?.scrollBy({ left: direction * 4 * WEEK * dayWidth.value, behavior: "smooth" })
		return
	}
	month.value = new Date(month.value.getFullYear(), month.value.getMonth() + direction, 1)
}
function goToday() {
	month.value = new Date(now.getFullYear(), now.getMonth(), 1)
	if (view.value === "timeline") scrollToDate(thisWeek)
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

const gridDays = computed(() => {
	const days = []
	for (let date = gridStart.value; date <= gridEnd.value; date = addDays(date, 1)) {
		days.push({
			iso: iso(date),
			day: date.getDate(),
			inMonth: date.getMonth() === month.value.getMonth(),
			weekend: [0, 6].includes(date.getDay()),
		})
	}
	return days
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
function absencesOn(date) {
	const result = []
	for (const employee of employees.value) {
		const absence = absenceDays.value[employee.employee]?.[date]
		if (!absence) continue
		result.push({
			employee: employee.employee,
			name: employee.employee_name,
			image: employee.image,
			requested: absence.requested,
			half: absence.half,
			title: absenceTitle(employee.employee_name, date, absence),
		})
	}
	return result
}

function absenceTitle(name, date, absence) {
	const what = absence.requested ? __("Absent (requested)") : __("Absent")
	return `${name} · ${formatDate(date)} · ${what}${absence.half ? ` · ${__("Half day")}` : ""}`
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
