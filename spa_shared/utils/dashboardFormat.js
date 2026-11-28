// Formatting helpers for cockpit dashboards (number cards, bars). Pure: no DOM, no Vue,
// so they run under Vitest. `formatComparison` keeps the exact wording the checklist
// dashboard used before it moved onto these helpers.
import { __ } from "./i18n.js"

export function formatComparison(current, previous, kind = "number") {
	if (current == null || previous == null) return __("No comparison")
	const delta = Number(current) - Number(previous)
	const sign = delta > 0 ? "+" : ""
	if (kind === "percent") return __("{0}pp", [`${sign}${delta.toFixed(1)}`])
	if (kind === "days") return __("{0}d", [`${sign}${delta.toFixed(1)}`])
	if (kind === "level") return `${sign}${delta}`
	if (!Number(previous)) return Number(current) ? __("New") : __("No change")
	const percent = (delta / Number(previous)) * 100
	return `${percent > 0 ? "+" : ""}${percent.toFixed(0)}%`
}

export function barHeight(value, max) {
	if (!value) return 0
	return Math.max(4, (Number(value) / Number(max || 1)) * 100)
}

export function pluralize(count, one, many) {
	return `${count} ${count === 1 ? one : many}`
}

export function ageLabel(days) {
	if (days == null) return ""
	if (days < 1) return __("today")
	return days === 1 ? __("{0} day", [days]) : __("{0} days", [days])
}

export function formatDays(value) {
	if (value == null) return "—"
	const rounded = Math.round(Number(value) * 10) / 10
	return rounded === 1 ? __("{0} day", [rounded]) : __("{0} days", [rounded])
}

/** Backlog change of one bar: positive means it grew. */
export function netLabel(net) {
	if (!net) return "±0"
	return net > 0 ? `+${net}` : `${net}`
}
