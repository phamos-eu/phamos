/**
 * Shared CSS grid for the Follow Ups filter bar + LeadList rows so columns
 * stay aligned. Order: name/company (search) | status | next follow up |
 * next step | last updated | owner. Owner sits last to match the MIS list's
 * "Assigned To" column. No priority column (Leads have none) and no
 * trailing "New" button column (Lead creation is out of scope here).
 */
export const LEAD_LIST_FILTER_GRID =
	"grid grid-cols-[minmax(0,1.4fr)_minmax(0,1.4fr)_minmax(0,1fr)_minmax(0,1.3fr)_minmax(0,1fr)_minmax(0,0.95fr)] gap-x-6"

/** Toolbar / row that participates in the parent LEAD_LIST_FILTER_GRID tracks */
export const LEAD_LIST_FILTER_SUBGRID = "col-span-6 grid grid-cols-subgrid items-center"

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

export const LEAD_STATUS_THEMES = {
	Lead: "gray",
	Open: "blue",
	Replied: "blue",
	Opportunity: "orange",
	Quotation: "orange",
	"Lost Quotation": "gray",
	Interested: "green",
	Converted: "green",
	"Do Not Contact": "red",
}

export function leadStatusTheme(status) {
	return LEAD_STATUS_THEMES[status] || "gray"
}
