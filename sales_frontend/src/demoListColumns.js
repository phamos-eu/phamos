/**
 * Shared CSS grid for the Demos filter bar + list rows so columns stay
 * aligned. Order: subject/lead (search) | status | scheduled | last updated.
 */
export const DEMO_LIST_FILTER_GRID =
	"grid grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)] gap-x-6"

/** Toolbar / row that participates in the parent DEMO_LIST_FILTER_GRID tracks */
export const DEMO_LIST_FILTER_SUBGRID = "col-span-4 grid grid-cols-subgrid items-center"

export const DEMO_STATUS_THEMES = {
	Planned: "blue",
	Completed: "green",
	Cancelled: "gray",
}

export function demoStatusTheme(status) {
	return DEMO_STATUS_THEMES[status] || "gray"
}
