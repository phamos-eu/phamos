// Return times of Ophice's "Away" status (#2053). The server keeps an instant in UTC; every
// viewer reads it on their own clock, and sees the absent person's clock too when it differs.

function lang() {
	return (typeof window !== "undefined" && window.frappe?.boot?.lang) || undefined
}

/** The browser's IANA time zone, e.g. "Europe/Berlin". */
export function myZone() {
	try {
		return Intl.DateTimeFormat().resolvedOptions().timeZone || ""
	} catch {
		return ""
	}
}

function sameDay(a, b, timeZone) {
	const day = new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" })
	return day.format(a) === day.format(b)
}

/** "14:00", or "Mon 14:00" when it isn't today, in `timeZone` (default: the viewer's). */
export function clockTime(date, now = new Date(), timeZone = undefined) {
	const options = { hour: "2-digit", minute: "2-digit", timeZone }
	if (!sameDay(date, now, timeZone)) options.weekday = "short"
	return new Intl.DateTimeFormat(lang(), options).format(date)
}

/** "in 2 hours", "in 25 minutes", "5 minutes ago", in the user's language. */
export function relativeTime(date, now = new Date()) {
	const minutes = Math.round((date - now) / 60000)
	const format = new Intl.RelativeTimeFormat(lang(), { numeric: "auto" })
	if (Math.abs(minutes) < 60) return format.format(minutes, "minute")
	const hours = Math.round(minutes / 60)
	if (Math.abs(hours) < 48) return format.format(hours, "hour")
	return format.format(Math.round(hours / 24), "day")
}

/** Their local time and place, when their clock shows something else than mine; else null. */
export function theirClock(date, zone, now = new Date()) {
	if (!zone) return null
	try {
		const theirs = clockTime(date, now, zone)
		if (theirs === clockTime(date, now)) return null
		return { time: theirs, place: zone.split("/").pop().replace(/_/g, " ") }
	} catch {
		return null
	}
}

/** "2026-11-22T14:00" in local time, as a datetime-local input wants it. */
export function toLocalInput(date) {
	const pad = (n) => String(n).padStart(2, "0")
	return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}
