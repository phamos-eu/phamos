/**
 * Shared CSS grid for MIS filter bar + list rows so columns stay aligned.
 * Order: ID | Implementation | Month | Status | Total Hours | Billable Hours | Delta | Assigned To
 */
export const MIS_LIST_FILTER_GRID =
	"grid grid-cols-[minmax(0,0.85fr)_minmax(0,1.2fr)_minmax(0,0.85fr)_minmax(0,0.85fr)_minmax(0,0.7fr)_minmax(0,0.7fr)_minmax(0,0.85fr)_minmax(0,0.95fr)] gap-x-4"

/** Toolbar / row that participates in the parent MIS_LIST_FILTER_GRID tracks */
export const MIS_LIST_FILTER_SUBGRID = "col-span-8 grid grid-cols-subgrid items-center"

export const MIS_STATUSES = ["Draft", "Open", "Closed"]

export const MIS_MONTHS = [
	"January",
	"February",
	"March",
	"April",
	"May",
	"June",
	"July",
	"August",
	"September",
	"October",
	"November",
	"December",
]

/**
 * Match Desk list indicators for Monthly Implementation Summary
 * (Draft=red, Open=orange, Closed=green).
 */
export const MIS_STATUS_THEMES = {
	Draft: "red",
	Open: "orange",
	Closed: "green",
}

export const MIS_STATUS_STRONG_CLASSES = {
	Draft: "bg-red-600 text-white dark:bg-red-500",
	Open: "bg-amber-500 text-white dark:bg-amber-500",
	Closed: "bg-green-600 text-white dark:bg-green-500",
}

/** Fixed thresholds for non-billable share of total hours. */
export const MIS_DELTA_GREEN_MAX = 0.1
export const MIS_DELTA_AMBER_MAX = 0.25

export function misStatusTheme(status) {
	return MIS_STATUS_THEMES[status] || "gray"
}

export function formatMisPeriod(row) {
	const parts = [row?.month, row?.year].filter(Boolean)
	return parts.length ? parts.join(" ") : "—"
}

/**
 * Color tone for delta ratio: green ≤10%, amber ≤25%, red above, gray when undefined.
 * @param {number|null|undefined} ratio
 * @returns {"green"|"amber"|"red"|"gray"}
 */
export function misDeltaTone(ratio) {
	if (ratio == null || Number.isNaN(Number(ratio))) return "gray"
	const value = Number(ratio)
	if (value <= MIS_DELTA_GREEN_MAX) return "green"
	if (value <= MIS_DELTA_AMBER_MAX) return "amber"
	return "red"
}

export function formatHours(value) {
	const n = Number(value)
	if (!Number.isFinite(n)) return "—"
	return n.toLocaleString(undefined, {
		minimumFractionDigits: 0,
		maximumFractionDigits: 2,
	})
}

export function formatDeltaPercent(ratio) {
	if (ratio == null || Number.isNaN(Number(ratio))) return "—"
	return `${(Number(ratio) * 100).toLocaleString(undefined, {
		minimumFractionDigits: 0,
		maximumFractionDigits: 1,
	})}%`
}

const MIS_DELTA_TEXT_CLASSES = {
	green: "text-green-700 dark:text-green-400",
	amber: "text-amber-700 dark:text-amber-400",
	red: "text-red-700 dark:text-red-400",
	gray: "text-ink-gray-6",
}

export function misDeltaTextClass(ratio) {
	return MIS_DELTA_TEXT_CLASSES[misDeltaTone(ratio)]
}

