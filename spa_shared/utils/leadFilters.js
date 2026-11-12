// Filters that carry a figure of the Sales Cockpit's lead overview into the lead list and into Desk
// (phamos/phamos#1758). Pure: no DOM, no Vue, so they run under Vitest.
import { __ } from "./i18n.js"

/** Which overview view (All / Inbound / Outbound) a list was opened from, for the way back. */
export const OVERVIEW_BACK_KEY = "overview"

/** URL query keys the list understands; the same names as `sales_leads.get_leads` takes. */
export const LEAD_FILTER_KEYS = ["created_from", "created_to", "direction", "source", "status"]

/** "none" means "not set" for direction and source. */
export const NOT_SET = "none"

/** The overview filters in a route query, or {} when none is set. */
export function leadFiltersFromQuery(query = {}) {
	const filters = {}
	for (const key of LEAD_FILTER_KEYS) {
		const value = query[key]
		if (typeof value === "string" && value) filters[key] = value
	}
	return filters
}

export function hasLeadFilters(filters) {
	return Object.keys(filters || {}).length > 0
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

/** "Nov 2026" for "2026-11" or "2026-11-01". */
export function monthLabel(value) {
	const [year, month] = String(value || "").split("-").map(Number)
	if (!year || !month) return ""
	return `${__(MONTHS[month - 1])} ${year}`
}

function lastDayOfMonth(year, month) {
	return new Date(Date.UTC(year, month, 0)).getUTCDate()
}

/** "Nov 2026" for a whole month, "1 Nov 2026 – 12 Nov 2026" otherwise. */
export function createdRangeLabel(from, to) {
	if (!from && !to) return ""
	const [fy, fm, fd] = (from || "").split("-").map(Number)
	const [ty, tm, td] = (to || "").split("-").map(Number)
	const day = (y, m, d) => `${d} ${__(MONTHS[m - 1])} ${y}`
	if (from && to && fy === ty && fm === tm && fd === 1 && td === lastDayOfMonth(ty, tm)) {
		return `${__(MONTHS[fm - 1])} ${fy}`
	}
	if (from && to) return `${day(fy, fm, fd)} – ${day(ty, tm, td)}`
	return from ? __("from {0}", [day(fy, fm, fd)]) : __("until {0}", [day(ty, tm, td)])
}

/**
 * Removable chips for the active filters: [{ keys, label }]. Removing a chip drops all its `keys`
 * (the created range is one chip).
 */
export function leadFilterChips(filters = {}) {
	const chips = []
	if (filters.created_from || filters.created_to) {
		chips.push({
			keys: ["created_from", "created_to"],
			label: __("Created: {0}", [createdRangeLabel(filters.created_from, filters.created_to)]),
		})
	}
	if (filters.direction) {
		chips.push({ keys: ["direction"], label: filters.direction === NOT_SET ? __("Inbound / Outbound: not set") : __(filters.direction) })
	}
	if (filters.source) {
		chips.push({ keys: ["source"], label: filters.source === NOT_SET ? __("No source") : __("Source: {0}", [filters.source]) })
	}
	if (filters.status) chips.push({ keys: ["status"], label: __("Status: {0}", [__(filters.status)]) })
	return chips
}

/** Desk's Lead list with the same filters: bulk edit, export and group-by come with it. */
export function leadDeskListUrl(filters = {}) {
	const params = new URLSearchParams()
	const json = (value) => JSON.stringify(value)
	const { created_from: from, created_to: to } = filters
	if (from && to) params.set("creation", json(["Between", [from, to]]))
	else if (from) params.set("creation", json([">=", from]))
	// A date alone compares with midnight on a Datetime: include the whole last day.
	else if (to) params.set("creation", json(["<=", `${to} 23:59:59`]))
	if (filters.direction) {
		params.set("custom_lead_direction", filters.direction === NOT_SET ? json(["is", "not set"]) : filters.direction)
	}
	if (filters.source) params.set("source", filters.source === NOT_SET ? json(["is", "not set"]) : filters.source)
	if (filters.status) params.set("status", filters.status)
	const query = params.toString()
	return query ? `/app/lead?${query}` : "/app/lead"
}
