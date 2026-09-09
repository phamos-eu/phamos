/**
 * Shared CSS grid for IssuesInbox filter bar + IssueList rows so columns stay aligned.
 * Order: subject/search | priority | status | created on (+ age) | last updated | New Issue
 */
export const ISSUE_LIST_FILTER_GRID =
	"grid grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_auto] gap-x-6"

/** Toolbar / row that participates in the parent ISSUE_LIST_FILTER_GRID tracks */
export const ISSUE_LIST_FILTER_SUBGRID =
	"col-span-6 grid grid-cols-subgrid items-center"
