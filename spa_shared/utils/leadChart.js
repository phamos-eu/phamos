// Bars of the lead overview's monthly chart on "All leads" (phamos/phamos#1929, #1950). Pure: no DOM, no Vue,
// so it runs under Vitest. The view hands the result to PeriodBars.
import { __ } from "./i18n.js"
import { NOT_SET } from "./leadFilters.js"

/** "side": Inbound, Outbound and Total each next to the same month a year earlier. "stacked": mix per bar. */
export const CHART_MODES = ["side", "stacked"]
export const DEFAULT_CHART_MODE = "side"
export const YEAR_EARLIER_OPACITY = 0.4

const BLUE = "var(--ink-blue-3)"
const GREEN = "var(--ink-green-3)"
const AMBER = "var(--ink-amber-3)"
const GREY = "var(--ink-gray-6)"

/** The chart mode to use for a stored value: anything unknown (or nothing stored) falls back to the default. */
export function chartMode(value) {
	return CHART_MODES.includes(value) ? value : DEFAULT_CHART_MODE
}

function bar(value, color, label, yearEarlier) {
	return {
		value: Number(value) || 0,
		color,
		opacity: yearEarlier ? YEAR_EARLIER_OPACITY : 1,
		label: yearEarlier ? `${label} · ${__("Same month a year earlier")}` : label,
	}
}

function stackedParts() {
	return [
		{ key: "Inbound", label: __("Inbound"), color: BLUE },
		{ key: "Outbound", label: __("Outbound"), color: GREEN },
		{ key: NOT_SET, label: __("Not set"), color: AMBER },
	]
}

function sideParts() {
	return [
		{ key: "Inbound", label: __("Inbound"), color: BLUE },
		{ key: "Outbound", label: __("Outbound"), color: GREEN },
		{ key: "total", label: __("Total"), color: GREY },
	]
}

/** Legend entries for a mode. */
export function chartLegend(mode) {
	return (mode === "stacked" ? stackedParts() : sideParts()).map(({ label, color }) => ({ label, color }))
}

/**
 * The bar values of one chart month (`month` as `build_overview` sends it: count, split, last_year,
 * last_year_split). A month without history (`last_year` null) gets no year-earlier bars: value 0 draws nothing.
 */
export function chartValues(month, mode) {
	if (mode === "stacked") {
		const segments = (split, yearEarlier) =>
			stackedParts().map((part) => bar(split?.[part.key], part.color, part.label, yearEarlier))
		return [segments(month.split, false), segments(month.last_year_split, true)]
	}
	// Total includes the leads not marked Inbound or Outbound, so it matches the footer number.
	const now = { ...month.split, total: month.count }
	const before = month.last_year == null ? {} : { ...month.last_year_split, total: month.last_year }
	return sideParts().flatMap((part) => [
		bar(now[part.key], part.color, part.label, false),
		bar(before[part.key], part.color, part.label, true),
	])
}
