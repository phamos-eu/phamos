import dayjs from "dayjs"
import utc from "dayjs/plugin/utc"
import timezone from "dayjs/plugin/timezone"
import customParseFormat from "dayjs/plugin/customParseFormat"

dayjs.extend(utc)
dayjs.extend(timezone)
dayjs.extend(customParseFormat)

function boot() {
	return typeof window !== "undefined" && window.frappe?.boot ? window.frappe.boot : {}
}

function timeZones() {
	const b = boot()
	const tz = b.time_zone || b.timezone || {}
	return {
		system: tz.system || "",
		user: tz.user || tz.system || "",
	}
}

export function getDateFormat() {
	return boot().sysdefaults?.date_format || "dd.mm.yyyy"
}

export function getTimeFormat() {
	return boot().sysdefaults?.time_format || "HH:mm:ss"
}

const WEEKDAY_NAMES = [
	"Sunday",
	"Monday",
	"Tuesday",
	"Wednesday",
	"Thursday",
	"Friday",
	"Saturday",
]
const WEEKDAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

export function getFirstDayOfWeek() {
	return boot().sysdefaults?.first_day_of_the_week || "Sunday"
}

/** JS Date.getDay() index (0=Sunday) for the configured first day of the week. */
export function getFirstDayOfWeekIndex() {
	const idx = WEEKDAY_NAMES.indexOf(getFirstDayOfWeek())
	return idx >= 0 ? idx : 0
}

/** Short weekday labels rotated to match System Settings first day of the week. */
export function getWeekdayLabels() {
	const start = getFirstDayOfWeekIndex()
	return [...WEEKDAY_LABELS.slice(start), ...WEEKDAY_LABELS.slice(0, start)]
}

/** Calendar month header, e.g. "August 2026". */
export function formatMonthYear(date) {
	if (!date) return ""
	const d = dayjs(date)
	return d.isValid() ? d.format("MMMM YYYY") : ""
}

function pad(n) {
	return String(n).padStart(2, "0")
}

/** Format YYYY-MM-DD HH:mm:ss string using system date/time format tokens. */
function fmtStr(dtStr) {
	if (!dtStr) return "—"
	const parts = String(dtStr).split(/[- :]/)
	if (parts.length < 5) return dtStr
	const [y, mo, dd, hh, mm, ss = "00"] = parts
	const dateFormat = getDateFormat()
	const timeFormat = getTimeFormat()
	const datePart = dateFormat
		.replace("dd", pad(dd))
		.replace("mm", pad(mo))
		.replace("yyyy", y)
	const timePart = timeFormat.includes("ss")
		? `${pad(hh)}:${pad(mm)}:${pad(ss)}`
		: `${pad(hh)}:${pad(mm)}`
	return `${datePart} ${timePart}`
}

/** Date-only field (YYYY-MM-DD) using system date format. */
export function formatDate(value) {
	if (!value) return "—"
	const str = String(value).trim()
	const parts = str.split(/[-/]/)
	if (parts.length < 3) return str
	let y, mo, dd
	if (parts[0].length === 4) {
		[y, mo, dd] = parts
	} else {
		[dd, mo, y] = parts
	}
	const dateFormat = getDateFormat()
	return dateFormat.replace("dd", pad(dd)).replace("mm", pad(mo)).replace("yyyy", y)
}

/** System-tz datetime string → user-tz display. */
export function formatDatetime(dtStr) {
	if (!dtStr) return "—"
	const { system, user } = timeZones()
	if (system && user) {
		try {
			const normalized = String(dtStr).replace("T", " ").slice(0, 19)
			const m = dayjs.tz(normalized, "YYYY-MM-DD HH:mm:ss", system).tz(user)
			if (m.isValid()) {
				return fmtStr(m.format("YYYY-MM-DD HH:mm:ss"))
			}
		} catch {
			/* fall through */
		}
	}
	return fmtStr(String(dtStr).replace("T", " ").slice(0, 19))
}

/** User-local Date (datetime-local semantics) → system-tz API string. */
export function formatForApi(date) {
	if (!date || !(date instanceof Date) || isNaN(date)) return null
	const localStr = `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:00`
	const { system, user } = timeZones()
	if (system && user) {
		try {
			return dayjs.tz(localStr, "YYYY-MM-DD HH:mm:ss", user).tz(system).format("YYYY-MM-DD HH:mm:ss")
		} catch {
			/* fall through */
		}
	}
	return localStr
}

/** System-tz datetime string → local Date for datetime-local inputs. */
export function parseSystemDatetimeToUserDate(dtStr) {
	if (!dtStr || typeof dtStr !== "string") return null
	const { system, user } = timeZones()
	if (system && user) {
		try {
			const normalized = dtStr.replace("T", " ").slice(0, 19)
			const m = dayjs.tz(normalized, "YYYY-MM-DD HH:mm:ss", system).tz(user)
			if (m.isValid()) {
				return new Date(m.year(), m.month(), m.date(), m.hour(), m.minute(), m.second())
			}
		} catch {
			/* fall through */
		}
	}
	const parts = dtStr.split(/[- :]/).map(Number)
	if (parts.length < 5 || parts.some(Number.isNaN)) return null
	const [y, mo, dd, hh, mm, ss = 0] = parts
	return new Date(y, mo - 1, dd, hh, mm, ss)
}

export function isSameCalendarDate(a, b) {
	if (!a || !b) return false
	return (
		a.getFullYear() === b.getFullYear() &&
		a.getMonth() === b.getMonth() &&
		a.getDate() === b.getDate()
	)
}

/** Seconds elapsed since a system-tz datetime string (for pause timers). */
export function secondsSinceSystemDatetime(dtStr) {
	if (!dtStr) return 0
	const { system } = timeZones()
	if (system) {
		try {
			const normalized = String(dtStr).replace("T", " ").slice(0, 19)
			const from = dayjs.tz(normalized, "YYYY-MM-DD HH:mm:ss", system)
			if (from.isValid()) {
				return Math.max(0, dayjs().tz(system).diff(from, "second"))
			}
		} catch {
			/* fall through */
		}
	}
	const from = new Date(String(dtStr).replace(" ", "T"))
	return Math.max(0, Math.round((Date.now() - from.getTime()) / 1000))
}

/** Human-readable duration from seconds (e.g. 2m 15s). */
export function formatDurationShort(seconds) {
	const s = Math.abs(Math.round(seconds || 0))
	const h = Math.floor(s / 3600)
	const m = Math.floor((s % 3600) / 60)
	const sec = s % 60
	if (h > 0) return `${h}h ${m}m`
	if (m > 0) return `${m}m ${sec}s`
	return `${sec}s`
}

/** Gantt day header label mode from zoom (px per day). */
export function getGanttDayLabelMode(zoom) {
	if (zoom >= 40) return "full"
	if (zoom >= 27) return "short"
	return "dayOnly"
}

const DAYJS_LOCALES = {
	de: () => import("dayjs/locale/de"),
	fr: () => import("dayjs/locale/fr"),
	es: () => import("dayjs/locale/es"),
	it: () => import("dayjs/locale/it"),
	nl: () => import("dayjs/locale/nl"),
	pt: () => import("dayjs/locale/pt"),
	pl: () => import("dayjs/locale/pl"),
}

const loadedLocales = new Set(["en"])

function bootLang() {
	const lang = boot().lang || boot().language || "en"
	return String(lang).split(/[-_]/)[0].toLowerCase()
}

function localizedDayjs(date) {
	const d = dayjs(date)
	if (!d.isValid()) return d
	const lang = bootLang()
	if (lang === "en" || !DAYJS_LOCALES[lang]) return d
	if (loadedLocales.has(lang)) return d.locale(lang)
	loadedLocales.add(lang)
	DAYJS_LOCALES[lang]().then((mod) => {
		dayjs.locale(mod.default || mod)
	})
	return d
}

function firstGrapheme(str) {
	if (!str) return ""
	if (typeof Intl !== "undefined" && Intl.Segmenter) {
		const segments = [...new Intl.Segmenter(undefined, { granularity: "grapheme" }).segment(str)]
		return segments[0]?.segment || str.charAt(0)
	}
	return str.charAt(0)
}

/** Locale-aware Gantt day column label; zoom abbreviates weekday but keeps day number. */
export function formatGanttDayLabel(date, zoom) {
	const mode = getGanttDayLabelMode(zoom)
	const d = localizedDayjs(date)
	if (!d.isValid()) return ""
	const dayNum = d.date()
	const weekday = d.format("ddd")
	if (mode === "dayOnly") return String(dayNum)
	if (mode === "short") return `${firstGrapheme(weekday)} ${dayNum}`
	return `${weekday} ${dayNum}`
}

/** Time portion of a datetime using system time format. */
export function formatTime(dtStr) {
	if (!dtStr) return "—"
	const timeFormat = getTimeFormat()
	const { system, user } = timeZones()
	if (system && user) {
		try {
			const normalized = String(dtStr).replace("T", " ").slice(0, 19)
			const m = dayjs.tz(normalized, "YYYY-MM-DD HH:mm:ss", system).tz(user)
			if (m.isValid()) {
				const fmt = timeFormat.includes("ss") ? "HH:mm:ss" : "HH:mm"
				return m.format(fmt)
			}
		} catch {
			/* fall through */
		}
	}
	const parts = String(dtStr).split(/[- :]/)
	if (parts.length >= 6) return `${pad(parts[3])}:${pad(parts[4])}`
	return "—"
}

/** Parse datetime-local input value to local Date. */
export function parseDatetimeLocalValue(str) {
	if (!str) return null
	const [datePart, timePart] = str.split("T")
	if (!datePart || !timePart) return null
	const [y, mo, dd] = datePart.split("-").map(Number)
	const [hh, mm] = timePart.split(":").map(Number)
	if ([y, mo, dd, hh, mm].some(Number.isNaN)) return null
	return new Date(y, mo - 1, dd, hh, mm, 0)
}

/** Local datetime for datetime-local input value attribute. */
export function toDatetimeLocalValue(date) {
	if (!date || !(date instanceof Date) || isNaN(date)) return ""
	return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

/** User timezone from boot (User.time_zone), falling back to system timezone. */
export function getUserTimeZone() {
	const { user, system } = timeZones()
	return user || system || ""
}

/** Current moment in the logged-in user's timezone. */
export function nowInUserTz() {
	const tz = getUserTimeZone()
	if (tz) {
		try {
			const m = dayjs().tz(tz)
			if (m.isValid()) return m
		} catch {
			/* fall through */
		}
	}
	return dayjs()
}

/** Calendar date YYYY-MM-DD in the user's timezone. */
export function todayIsoInUserTz() {
	return nowInUserTz().format("YYYY-MM-DD")
}

/**
 * Fraction of the calendar day elapsed in the user's timezone (0 at midnight, 1 at end of day).
 */
export function dayProgressFraction(moment = null) {
	const m = moment || nowInUserTz()
	const seconds = m.hour() * 3600 + m.minute() * 60 + m.second() + m.millisecond() / 1000
	return Math.min(1, Math.max(0, seconds / 86400))
}
