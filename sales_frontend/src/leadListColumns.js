import { __ } from "@spa/utils/i18n.js"

/**
 * Shared CSS grid for the Follow Ups filter bar + LeadList rows so columns
 * stay aligned. Order: name/company (search) | status | next follow up |
 * last updated | owner. Owner sits last to match the MIS list's
 * "Assigned To" column. No priority column (Leads have none) and no
 * trailing "New" button column (Lead creation is out of scope here).
 */
export const LEAD_LIST_FILTER_GRID =
	"grid grid-cols-[minmax(0,1.2fr)_minmax(0,1.6fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,0.95fr)] gap-x-6"

/** Toolbar / row that participates in the parent LEAD_LIST_FILTER_GRID tracks */
export const LEAD_LIST_FILTER_SUBGRID = "col-span-5 grid grid-cols-subgrid items-center"

export const LEAD_STATUSES = [
	"Lead",
	"Open",
	"Replied",
	"Opportunity",
	"Quotation",
	"Lost Quotation",
	"Interested",
	"Converted",
	"Do Not Contact",
]

export const QUALIFICATION_STATUSES = ["Unqualified", "In Process", "Qualified"]

export const NO_OF_EMPLOYEES_OPTIONS = ["1-10", "11-50", "51-200", "201-500", "501-1000", "1000+"]

export const REQUEST_TYPE_OPTIONS = ["Product Enquiry", "Request for Information", "Suggestions", "Other"]

/**
 * Desk colours Lead statuses through `frappe.utils.guess_colour`, which only
 * recognises two of the nine: Open is red and Converted is green — everything
 * else comes out gray. Those two are matched exactly; the rest are separated
 * along the pipeline instead of being left indistinguishable.
 */
export const LEAD_STATUS_THEMES = {
	Lead: "gray",
	Open: "red",
	Replied: "blue",
	Interested: "blue",
	Opportunity: "orange",
	Quotation: "orange",
	"Lost Quotation": "gray",
	Converted: "green",
	// Desk shows this gray; kept red here because it's the one status that
	// means stop, and the cockpit already treats it specially.
	"Do Not Contact": "red",
}

export function leadStatusTheme(status) {
	return LEAD_STATUS_THEMES[status] || "gray"
}

/** A status as the user reads it. The stored value stays English. */
export function leadStatusLabel(status) {
	return __(status)
}

const STRONG_BY_THEME = {
	red: "bg-red-600 text-white dark:bg-red-500",
	blue: "bg-blue-600 text-white dark:bg-blue-500",
	orange: "bg-amber-500 text-white dark:bg-amber-500",
	green: "bg-green-600 text-white dark:bg-green-500",
	gray: "bg-gray-700 text-white dark:bg-gray-500",
}

/** Filled chip for the selected status, matching StatusFilter's selected look. */
export function leadStatusStrongClass(status) {
	return STRONG_BY_THEME[leadStatusTheme(status)] || STRONG_BY_THEME.gray
}
