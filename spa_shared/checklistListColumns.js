/** Shared grid for Checklist filter bar + list rows (full width). */
export const CHECKLIST_LIST_FILTER_GRID =
	"grid grid-cols-[minmax(0,1.35fr)_minmax(11rem,1fr)_minmax(4.5rem,0.55fr)_minmax(0,0.85fr)_minmax(0,0.85fr)_minmax(0,0.75fr)_auto] gap-x-4"

export const CHECKLIST_LIST_FILTER_SUBGRID =
	"col-span-7 grid grid-cols-subgrid items-center"

/** Compact grid when list shares the pane with detail (50/50). */
export const CHECKLIST_LIST_COMPACT_GRID =
	"grid grid-cols-[minmax(0,1.45fr)_minmax(9rem,0.9fr)_minmax(6.5rem,0.8fr)_minmax(2rem,0.55fr)] gap-x-3"

export const CHECKLIST_LIST_COMPACT_SUBGRID =
	"col-span-4 grid grid-cols-subgrid items-center"

export const CHECKLIST_STATUSES = ["Not Started", "In Progress", "Completed"]

export function checklistStatusTheme(status) {
	if (status === "Completed") return "green"
	if (status === "In Progress") return "orange"
	return "gray"
}

export function checklistProgressBarClass(status, percentage) {
	if (status === "Completed" || percentage >= 100) return "bg-green-500"
	if (!percentage) return "bg-surface-gray-3"
	return "bg-blue-500"
}
