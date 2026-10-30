/**
 * What buildGantt() should do with the frappe-gantt chart for the current task list.
 * frappe-gantt 0.6.1 can't derive a date range from zero tasks (its constructor throws
 * in setup_gantt_dates), so an empty list clears the chart and leaves the empty state;
 * the next non-empty list then creates a fresh one.
 *
 * @returns {"clear" | "create" | "update"}
 */
export function ganttBuildAction(hasChart, taskCount) {
	if (!taskCount) return "clear"
	return hasChart ? "update" : "create"
}
