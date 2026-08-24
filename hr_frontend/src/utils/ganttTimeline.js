import { formatGanttDayLabel, formatMonthYear, dayProgressFraction, todayIsoInUserTz } from "@iown/utils/datetime"
import { formatDateIso } from "./ganttTimelineFormat.js"

const MIN_FRAME_DAYS = 7

function startOfDay(date) {
	const d = new Date(date)
	d.setHours(0, 0, 0, 0)
	return d
}

function addDays(date, days) {
	const d = new Date(date)
	d.setDate(d.getDate() + days)
	return d
}

function isoWeekNumber(date) {
	const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()))
	d.setUTCDate(d.getUTCDate() + 4 - (d.getUTCDay() || 7))
	const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1))
	return Math.ceil(((d - yearStart) / 86400000 + 1) / 7)
}

function monthKey(date) {
	return `${date.getFullYear()}-${date.getMonth()}`
}

/** First day of current month through last day of month + 2 months. */
export function defaultFrameRange() {
	const now = new Date()
	const start = new Date(now.getFullYear(), now.getMonth(), 1)
	const end = new Date(now.getFullYear(), now.getMonth() + 3, 0)
	return { start: startOfDay(start), end: startOfDay(end) }
}

/** Expand frame to include task dates when they fall outside the default window. */
export function expandFrameToTasks(taskDates, frameStart, frameEndInclusive) {
	let start = startOfDay(frameStart)
	let end = startOfDay(frameEndInclusive)

	if (taskDates.length) {
		const min = startOfDay(new Date(Math.min(...taskDates.map((d) => d.getTime()))))
		const max = startOfDay(new Date(Math.max(...taskDates.map((d) => d.getTime()))))
		if (min < start) start = min
		if (max > end) end = max
	}

	const spanDays = (end - start) / 86400000
	if (spanDays < MIN_FRAME_DAYS - 1) {
		end = addDays(start, MIN_FRAME_DAYS - 1)
	}

	return { start, end }
}

export function normalizeFrameRange(frameStart, frameEndInclusive) {
	let start = startOfDay(frameStart)
	let end = startOfDay(frameEndInclusive)
	if (end < start) end = new Date(start)
	const spanDays = (end - start) / 86400000
	if (spanDays < MIN_FRAME_DAYS - 1) {
		end = addDays(start, MIN_FRAME_DAYS - 1)
	}
	return { start, end }
}

/**
 * Build aligned month / week / day header segments.
 * rangeEndInclusive is the last visible day (inclusive).
 */
export function buildTimeline(rangeStart, rangeEndInclusive, columnWidth, zoom = 38) {
	if (!rangeStart || !rangeEndInclusive || columnWidth <= 0) {
		return {
			days: [],
			weeks: [],
			months: [],
			totalWidth: 0,
			rangeStart: null,
			rangeEnd: null,
			rangeEndInclusive: null,
		}
	}

	const start = startOfDay(rangeStart)
	const endInclusive = startOfDay(rangeEndInclusive)
	const endExclusive = addDays(endInclusive, 1)
	const days = []
	let cursor = new Date(start)

	while (cursor < endExclusive) {
		const left = days.length * columnWidth
		const iso = formatDateIso(cursor)
		days.push({
			date: new Date(cursor),
			iso,
			left,
			width: columnWidth,
			label: formatGanttDayLabel(cursor, zoom),
			weekNumber: isoWeekNumber(cursor),
			monthLabel: formatMonthYear(cursor),
			monthKey: monthKey(cursor),
		})
		cursor = addDays(cursor, 1)
	}

	const weeks = []
	const months = []

	for (const day of days) {
		const weekKey = `${day.date.getFullYear()}-W${day.weekNumber}`
		const lastWeek = weeks[weeks.length - 1]
		if (!lastWeek || lastWeek.key !== weekKey) {
			weeks.push({
				key: weekKey,
				number: day.weekNumber,
				left: day.left,
				width: day.width,
				startIso: day.iso,
				endIso: day.iso,
			})
		} else {
			lastWeek.width += day.width
			lastWeek.endIso = day.iso
		}

		const lastMonth = months[months.length - 1]
		if (!lastMonth || lastMonth.key !== day.monthKey) {
			months.push({
				key: day.monthKey,
				label: day.monthLabel,
				left: day.left,
				width: day.width,
				startIso: day.iso,
				endIso: day.iso,
			})
		} else {
			lastMonth.width += day.width
			lastMonth.endIso = day.iso
		}
	}

	return {
		days,
		weeks,
		months,
		totalWidth: days.length * columnWidth,
		rangeStart: start,
		rangeEnd: endExclusive,
		rangeEndInclusive: endInclusive,
	}
}

/** Today column overlay: full-day strip + now-line x within the day (user TZ). */
export function todayStripRect(timeline) {
	if (!timeline?.days?.length || !timeline.rangeStart) return null
	const todayIso = todayIsoInUserTz()
	const today = startOfDay(new Date(`${todayIso}T00:00:00`))
	const start = timeline.rangeStart
	const end = timeline.rangeEnd
	if (today < start || today >= end) return null
	const columnWidth = timeline.days[0].width
	const days = (today - start) / 86400000
	const left = days * columnWidth
	const fraction = dayProgressFraction()
	const edgeLeft = left + fraction * columnWidth
	return {
		left,
		width: columnWidth,
		edgeLeft,
	}
}

export function scrollLeftForDate(timeline, date, viewportWidth = 0) {
	if (!timeline?.days?.length || !date) return 0
	const target = startOfDay(date)
	const start = timeline.rangeStart
	const days = (target - start) / 86400000
	const left = days * timeline.days[0].width
	return Math.max(0, left - viewportWidth / 2 + timeline.days[0].width / 2)
}

export { formatDateIso } from "./ganttTimelineFormat.js"
