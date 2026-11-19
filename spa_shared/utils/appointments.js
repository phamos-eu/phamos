/**
 * Company appointments (#1949): repeats as the Mailcow invite has them, so the cockpit's list and
 * calendar show the same days as the attendees' calendars. Mirrors _row_recurrence_rule in
 * phamos/events/team_daily_schedule.py:
 * - Daily, Weekly, Monthly, Yearly, until the end of `repeat_till` (inclusive)
 * - Weekly on the ticked weekdays, or the weekday of the start when none is ticked
 * - Monthly / Yearly on the start's day; months without that day are skipped (RFC 5545)
 * Kept free of Vue and the DOM so it can be unit-tested.
 */

export const WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
const FREQUENCIES = ["Daily", "Weekly", "Monthly", "Yearly"]
// Safety cap for the expansion loops. They start at the window, not at the first occurrence
// (AI review of !1203), so this only limits how far one window reaches.
const MAX_STEPS = 5000
const DAY_MS = 86400000

/** "2026-12-01 10:00:00" (site time, as Frappe sends it) -> local Date. */
export function parseDateTime(value) {
	if (!value) return null
	if (value instanceof Date) return new Date(value)
	const [datePart, timePart = "00:00:00"] = String(value).trim().split(/[ T]/)
	const [y, m, d] = datePart.split("-").map(Number)
	const [hh = 0, mm = 0, ss = 0] = timePart.split(":").map((n) => Number.parseFloat(n))
	const date = new Date(y, m - 1, d, hh, mm, Math.floor(ss))
	return Number.isNaN(date.getTime()) ? null : date
}

/** Monday = 0 … Sunday = 6, as Python's weekday(). */
function weekdayIndex(date) {
	return (date.getDay() + 6) % 7
}

export function repeatFrequency(appointment) {
	if (!Number(appointment.repeat_this_event)) return null
	return FREQUENCIES.includes(appointment.repeat_on) ? appointment.repeat_on : null
}

/** Weekdays (0 = Monday) a weekly repeat falls on. */
export function weeklyDays(appointment) {
	const ticked = WEEKDAYS.map((day, i) => (Number(appointment[day]) ? i : -1)).filter((i) => i >= 0)
	if (ticked.length) return ticked
	const start = parseDateTime(appointment.start)
	return start ? [weekdayIndex(start)] : []
}

function repeatEnd(appointment) {
	const until = parseDateTime(appointment.repeat_till)
	if (!until) return null
	until.setHours(23, 59, 59, 999)
	return until
}

function addDays(date, days) {
	const d = new Date(date)
	d.setDate(d.getDate() + days)
	return d
}

/** Start of the n-th month/year after `start`, or null when that month lacks the start's day. */
function shiftMonths(start, months) {
	const d = new Date(start.getFullYear(), start.getMonth() + months, 1, start.getHours(), start.getMinutes(), start.getSeconds())
	d.setDate(start.getDate())
	return d.getDate() === start.getDate() ? d : null
}

/**
 * Occurrence starts in order, from the first one that can end at or after `fromDate` (the loops
 * jump there, one step early for daylight saving), up to `limitDate` or `repeat_till`.
 */
function* occurrenceStarts(appointment, fromDate, limitDate) {
	const start = parseDateTime(appointment.start)
	if (!start) return
	const freq = repeatFrequency(appointment)
	if (!freq) {
		yield start
		return
	}
	const until = repeatEnd(appointment)
	const stop = until && until < limitDate ? until : limitDate
	const within = (d) => d <= stop

	const behind = fromDate ? fromDate - start : 0
	if (freq === "Daily") {
		const first = Math.max(0, Math.floor(behind / DAY_MS) - 1)
		for (let i = first; i < first + MAX_STEPS; i++) {
			const d = addDays(start, i)
			if (!within(d)) return
			yield d
		}
	} else if (freq === "Weekly") {
		const days = weeklyDays(appointment)
		const weekStart = addDays(start, -weekdayIndex(start))
		const first = Math.max(0, Math.floor((fromDate ? fromDate - weekStart : 0) / (7 * DAY_MS)) - 1)
		for (let w = first; w < first + MAX_STEPS; w++) {
			for (const day of days) {
				const d = addDays(weekStart, w * 7 + day)
				if (d < start) continue
				if (!within(d)) return
				yield d
			}
		}
	} else {
		const step = freq === "Monthly" ? 1 : 12
		const monthsBehind = fromDate
			? (fromDate.getFullYear() - start.getFullYear()) * 12 + fromDate.getMonth() - start.getMonth()
			: 0
		const first = Math.max(0, Math.floor(monthsBehind / step) - 1)
		for (let i = first; i < first + MAX_STEPS; i++) {
			const d = shiftMonths(start, i * step)
			if (!d) continue
			if (!within(d)) return
			yield d
		}
	}
}

function duration(appointment) {
	const start = parseDateTime(appointment.start)
	const end = parseDateTime(appointment.end)
	return start && end && end > start ? end - start : 0
}

/** Occurrences ({ start, end } Dates) that overlap [from, to]. */
export function occurrencesBetween(appointment, from, to) {
	const length = duration(appointment)
	const result = []
	// An occurrence that started before `from` can still overlap it by its length.
	for (const start of occurrenceStarts(appointment, new Date(from.getTime() - length), to)) {
		const end = new Date(start.getTime() + length)
		if (end >= from && start <= to) result.push({ start, end })
	}
	return result
}

/** The first occurrence that hasn't ended at `now`, or null when all are past. */
export function nextOccurrence(appointment, now, horizonDays = 3660) {
	const length = duration(appointment)
	for (const start of occurrenceStarts(appointment, new Date(now.getTime() - length), addDays(now, horizonDays))) {
		const end = new Date(start.getTime() + length)
		if (end >= now) return { start, end }
	}
	return null
}

/**
 * The list: upcoming appointments by their next occurrence; with `includePast`, past ones after
 * them, newest first. Each item: { appointment, start, end, past }.
 */
export function listAppointments(appointments, now, includePast = false) {
	const upcoming = []
	const past = []
	for (const appointment of appointments || []) {
		const next = nextOccurrence(appointment, now)
		if (next) upcoming.push({ appointment, ...next, past: false })
		else if (includePast) {
			const start = parseDateTime(appointment.start)
			past.push({ appointment, start, end: new Date(start.getTime() + duration(appointment)), past: true })
		}
	}
	upcoming.sort((a, b) => a.start - b.start)
	past.sort((a, b) => b.start - a.start)
	return [...upcoming, ...past]
}
