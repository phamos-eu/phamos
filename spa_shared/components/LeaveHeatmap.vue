<template>
	<!--
		One row per month, one cell per day of the year, so a block of leave shows as a run of
		filled cells (#1836). A half day is filled on one diagonal half. Approved leave is green, a request blue; rejected and cancelled
		leave only an outline, red and dashed grey, as they never became an absence (PM,
		2026-11-07). Working days are a light fill, weekends and holidays an empty box. The date, type and
		status are in each cell's tooltip, so colour never carries identity alone.
		Used in the HR Cockpit's employee dialog and in My Leave in the Personal Cockpit.
	-->
	<div class="select-none">
		<div class="grid gap-y-1" :style="{ gridTemplateColumns: `2.25rem repeat(31, minmax(0, 1fr))` }">
			<template v-for="month in months" :key="month.index">
				<div :class="['pr-2 text-right text-xs leading-4', month.current ? 'font-semibold text-ink-gray-9' : 'text-ink-gray-5']">{{ month.label }}</div>
				<!--
					A leave cell is clickable: with `link` it goes there (URL in a new tab, or a route),
					without it it emits `select` so the caller can show the application in place.
					Plain branches, not <component :is="'button'">: a dynamic "button" resolves to the
					globally registered frappe-ui Button and inherits its size and colours.
				-->
				<template v-for="cell in month.cells" :key="cell.key">
					<a v-if="typeof cell.to === 'string'" :href="cell.to" target="_blank" rel="noopener" :class="cellClass(cell)" :style="cell.style" :title="cell.title" :aria-label="cell.title" />
					<RouterLink v-else-if="cell.to" :to="cell.to" :class="cellClass(cell)" :style="cell.style" :title="cell.title" :aria-label="cell.title" />
					<button
						v-else-if="cell.app"
						type="button"
						:class="cellClass(cell)"
						:style="cell.style"
						:title="cell.title"
						:aria-label="cell.title"
						:aria-pressed="cell.app.name === selected"
						@click="emit('select', cell.app)"
					/>
					<div v-else :class="cellClass(cell)" :style="cell.style" :title="cell.title" />
				</template>
			</template>
		</div>
		<div class="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-gray-6">
			<span class="text-ink-gray-5">{{ __("Click a leave day to see its application.") }}</span>
			<span class="inline-flex items-center gap-1.5"><span class="h-3 w-3 rounded-sm bg-surface-green-3" /> {{ __("Approved") }}</span>
			<span class="inline-flex items-center gap-1.5"><span class="h-3 w-3 rounded-sm bg-surface-blue-3" /> {{ __("Requested") }}</span>
			<span class="inline-flex items-center gap-1.5"><span class="h-3 w-3 rounded-sm" :style="halfStyle('--surface-green-3')" /> {{ __("Half day") }}</span>
			<span class="inline-flex items-center gap-1.5"><span class="h-3 w-3 rounded-sm border-2 border-outline-red-3" /> {{ __("Rejected") }}</span>
			<span class="inline-flex items-center gap-1.5"><span class="h-3 w-3 rounded-sm border-2 border-dashed border-outline-gray-4" /> {{ __("Cancelled") }}</span>
			<span class="inline-flex items-center gap-1.5"><span class="h-3 w-3 rounded-sm bg-surface-gray-2 ring-2 ring-[var(--ink-amber-3)]" /> {{ __("Today") }}</span>
			<span class="inline-flex items-center gap-1.5"><span class="h-3 w-3 rounded-sm bg-surface-gray-2" /> {{ __("Working day") }}</span>
			<span class="inline-flex items-center gap-1.5"><span class="h-3 w-3 rounded-sm border border-outline-gray-2" /> {{ __("Weekend or holiday") }}</span>
		</div>
	</div>
</template>

<script setup>
import { computed } from "vue"
import { RouterLink } from "vue-router"
import { formatDate } from "@spa/utils/datetime.js"
import { __ } from "@spa/utils/i18n.js"

const props = defineProps({
	year: { type: Number, required: true },
	/** Leave applications with name, from_date, to_date, leave_type, status; `neutral` ones carry only dates and status. */
	applications: { type: Array, default: () => [] },
	/** { date, description, weekly_off } from the employee's holiday list. */
	holidays: { type: Array, default: () => [] },
	/** application → a URL (opens in a new tab) or a router location. Without it a click emits `select`. */
	link: { type: Function, default: null },
	/** Name of the selected application; its days get a ring. */
	selected: { type: String, default: "" },
})
const emit = defineEmits(["select"])

/** Top-left half in the status colour, the rest like a working day; theme variables, so dark mode follows. */
function halfStyle(fill) {
	return { background: `linear-gradient(135deg, var(${fill}) 50%, var(--surface-gray-2) 50%)` }
}

/** The day of an application that is only half taken: HRMS uses half_day_date, or the only day. */
function halfDayOf(app) {
	if (!Number(app.half_day)) return null
	if (app.half_day_date) return String(app.half_day_date).slice(0, 10)
	const from = String(app.from_date).slice(0, 10)
	return from === String(app.to_date).slice(0, 10) ? from : null
}

function cellClass(cell) {
	return [
		"block h-4 w-full rounded-sm",
		cell.classes,
		cell.app
			? "hover:ring-2 hover:ring-outline-gray-4 focus:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
			: "",
		cell.app && cell.app.name === props.selected ? "ring-2 ring-outline-gray-5" : "",
		// Today, for orientation; amber is not a leave status. A selection's grey ring wins.
		cell.today && !(cell.app && cell.app.name === props.selected) ? "ring-2 ring-[var(--ink-amber-3)]" : "",
	]
}

// Rejected and cancelled applications never became an absence: they are drawn muted, and a
// real or planned absence on the same day wins over them.
const MUTED = ["Rejected", "Cancelled"]
const STATUS_STYLE = {
	Approved: { classes: "bg-surface-green-3", label: "Approved", fill: "--surface-green-3" },
	Open: { classes: "bg-surface-blue-3", label: "Requested", fill: "--surface-blue-3" },
	Rejected: { classes: "border-2 border-outline-red-3", label: "Rejected" },
	Cancelled: { classes: "border-2 border-dashed border-outline-gray-4", label: "Cancelled" },
}

const monthFormat = computed(() => {
	const lang = (typeof window !== "undefined" && window.frappe?.boot?.lang) || undefined
	return new Intl.DateTimeFormat(lang, { month: "short" })
})

const holidayByDate = computed(() => Object.fromEntries(props.holidays.map((h) => [String(h.date).slice(0, 10), h])))

const leaveByDate = computed(() => {
	const map = {}
	for (const app of props.applications) {
		const muted = MUTED.includes(app.status)
		const end = String(app.to_date).slice(0, 10)
		for (let date = String(app.from_date).slice(0, 10); date <= end; date = nextDay(date)) {
			if (muted && map[date] && !MUTED.includes(map[date].status)) continue
			map[date] = app
		}
	}
	return map
})

function iso(year, month, day) {
	return `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`
}

function nextDay(date) {
	const [y, m, d] = date.split("-").map(Number)
	const next = new Date(y, m - 1, d + 1)
	return iso(next.getFullYear(), next.getMonth(), next.getDate())
}

const todayIso = (() => {
	const d = new Date()
	return iso(d.getFullYear(), d.getMonth(), d.getDate())
})()

const months = computed(() =>
	Array.from({ length: 12 }, (_, index) => {
		const days = new Date(props.year, index + 1, 0).getDate()
		const cells = []
		for (let day = 1; day <= 31; day++) {
			if (day > days) {
				cells.push({ key: `${index}-${day}`, classes: "", title: "" })
				continue
			}
			const date = iso(props.year, index, day)
			const leave = leaveByDate.value[date]
			const holiday = holidayByDate.value[date]
			const weekend = [0, 6].includes(new Date(props.year, index, day).getDay())
			const today = date === todayIso
			const label = today ? `${formatDate(date)} · ${__("Today")}` : formatDate(date)
			if (leave) {
				const style = STATUS_STYLE[leave.status] || STATUS_STYLE.Open
				const half = halfDayOf(leave) === date
				cells.push({
					key: date,
					// A muted (outline) status keeps its outline on a half day; the tooltip names it.
					classes: half && style.fill ? "" : style.classes,
					style: half && style.fill ? halfStyle(style.fill) : null,
					// A neutral absence (sick leave in the HR view, #1838) names no type and opens nothing.
					title: `${label} · ${leave.neutral ? __("Absent") : __(leave.leave_type)}${half ? ` · ${__("Half day")}` : ""} · ${__(style.label)}`,
					today,
					app: leave.neutral ? null : leave,
					to: props.link && !leave.neutral ? props.link(leave) : null,
				})
			} else if (holiday || weekend) {
				// Recessive: an empty box, so the working-day grid and the leave blocks stand out.
				cells.push({
					key: date,
					classes: "border border-outline-gray-2",
					title: holiday && !holiday.weekly_off ? `${label} · ${holiday.description}` : label,
					today,
				})
			} else {
				cells.push({ key: date, classes: "bg-surface-gray-2", title: label, today })
			}
		}
		const current = props.year === new Date().getFullYear() && index === new Date().getMonth()
		return { index, label: monthFormat.value.format(new Date(props.year, index, 1)), cells, current }
	})
)
</script>
