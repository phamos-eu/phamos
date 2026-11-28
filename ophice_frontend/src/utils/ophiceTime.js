// Times in Ophice (#2053, #2066). The server keeps instants; every viewer reads them as their
// Frappe settings say (PM, 2026-11-22): the time zone of their user (else the system's), and the
// date and time format of System Settings. The absent person's own clock is shown too when it differs.
import { getDateFormat, getTimeFormat } from "@spa/utils/datetime.js"
import { __ } from "@spa/utils/i18n.js"

function boot() {
	return (typeof window !== "undefined" && window.frappe?.boot) || {}
}

function lang() {
	return boot().lang || undefined
}

/** The viewer's IANA time zone: their User setting, else the system's, else the browser's. */
export function myZone() {
	const tz = boot().time_zone || boot().timezone || {}
	if (tz.user || tz.system) return tz.user || tz.system
	try {
		return Intl.DateTimeFormat().resolvedOptions().timeZone || ""
	} catch {
		return ""
	}
}

/** Year, month, day, hour, minute, second of `date` on the clock of `timeZone`. */
function partsIn(date, timeZone) {
	const format = new Intl.DateTimeFormat("en-GB", {
		timeZone: timeZone || undefined,
		year: "numeric",
		month: "2-digit",
		day: "2-digit",
		hour: "2-digit",
		minute: "2-digit",
		second: "2-digit",
		hourCycle: "h23",
	})
	const parts = {}
	for (const part of format.formatToParts(date)) parts[part.type] = part.value
	return parts
}

/** "14:00" (with seconds when System Settings say so), or "24.11.2026 14:00" when it isn't today. */
export function clockTime(date, now = new Date(), timeZone = myZone()) {
	const p = partsIn(date, timeZone)
	const today = partsIn(now, timeZone)
	const time = getTimeFormat().includes("ss") ? `${p.hour}:${p.minute}:${p.second}` : `${p.hour}:${p.minute}`
	if (p.year === today.year && p.month === today.month && p.day === today.day) return time
	const day = getDateFormat().replace("dd", p.day).replace("mm", p.month).replace("yyyy", p.year)
	return `${day} ${time}`
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

/** "2026-11-22T14:00" on the viewer's clock (myZone), as a datetime-local input wants it. */
export function toLocalInput(date, timeZone = myZone()) {
	const p = partsIn(date, timeZone)
	return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`
}

/** The instant a datetime-local value ("2026-11-22T14:00") means on the viewer's clock. */
export function fromLocalInput(value, timeZone = myZone()) {
	const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(value || "")
	if (!match) return null
	const [, y, mo, d, h, mi] = match.map(Number)
	const wanted = Date.UTC(y, mo - 1, d, h, mi)
	// Guess as UTC, then shift by the zone's offset at that moment (twice: offsets change at DST).
	let instant = wanted
	for (let i = 0; i < 2; i++) {
		const p = partsIn(new Date(instant), timeZone)
		const shown = Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour, +p.minute)
		instant += wanted - shown
	}
	return new Date(instant)
}

/** Tomorrow at `hour`:00 on the viewer's clock. */
export function tomorrowAt(hour, timeZone = myZone()) {
	const p = partsIn(new Date(Date.now() + 86400000), timeZone)
	return fromLocalInput(`${p.year}-${p.month}-${p.day}T${String(hour).padStart(2, "0")}:00`, timeZone)
}

/** The age of a chat line in steps (#2066, PM 2026-11-22): "in the last 15 minutes", "… 30 …", … */
export function withinMinutes(date, now = new Date(), step = 15) {
	const minutes = Math.max(0, (now - date) / 60000)
	return __("in the last {0} minutes", [Math.max(step, Math.ceil(minutes / step) * step)])
}
