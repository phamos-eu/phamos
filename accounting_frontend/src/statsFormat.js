// Money and date formatting for the Accounting statistics and payment calendar.

const formatters = new Map()

function formatter(currency, compact) {
	const key = `${currency}|${compact}`
	if (!formatters.has(key)) {
		formatters.set(
			key,
			new Intl.NumberFormat(undefined, {
				style: "currency",
				currency: currency || "EUR",
				notation: compact ? "compact" : "standard",
				maximumFractionDigits: compact ? 1 : 2,
				minimumFractionDigits: compact ? 0 : 2,
			})
		)
	}
	return formatters.get(key)
}

export function formatMoney(value, currency, { compact = false } = {}) {
	if (value == null || Number.isNaN(Number(value))) return "—"
	return formatter(currency, compact).format(Number(value))
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

/** "2026-10-20" → Date at local midnight (no UTC shift). */
export function parseDay(value) {
	const [y, m, d] = String(value).split("-").map(Number)
	return new Date(y, m - 1, d)
}

export function dayKey(date) {
	const pad = (n) => String(n).padStart(2, "0")
	return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

export function shortDay(value) {
	const date = typeof value === "string" ? parseDay(value) : value
	return `${date.getDate()} ${MONTHS[date.getMonth()]}`
}

export function monthTitle(date) {
	return `${MONTHS[date.getMonth()]} ${date.getFullYear()}`
}

/** Monday-first 6×7 (or fewer) grid of days covering the month of `date`. */
export function monthGridDays(date) {
	const first = new Date(date.getFullYear(), date.getMonth(), 1)
	const last = new Date(date.getFullYear(), date.getMonth() + 1, 0)
	const start = new Date(first)
	start.setDate(first.getDate() - ((first.getDay() + 6) % 7))
	const end = new Date(last)
	end.setDate(last.getDate() + (6 - ((last.getDay() + 6) % 7)))
	const days = []
	for (const day = new Date(start); day <= end; day.setDate(day.getDate() + 1)) {
		days.push(new Date(day))
	}
	return days
}
