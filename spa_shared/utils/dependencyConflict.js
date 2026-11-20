// Date conflicts between dependent Tasks (#2002, slice 3 of #1999): show and warn only, no date
// changes by itself. Same rule as ConvertToTaskDialog's warning: starting on the day the
// predecessor ends is fine, starting earlier is a conflict.

function isoDay(value) {
	return value ? String(value).slice(0, 10) : ""
}

/**
 * The last day of a Task as its Gantt bar shows it: the expected end, else the expected start.
 * @param {{exp_start_date?: string, exp_end_date?: string}} task
 */
export function taskEndDay(task) {
	return isoDay(task?.exp_end_date) || isoDay(task?.exp_start_date)
}

/**
 * True when the successor starts before its predecessor ends. Missing dates are no conflict.
 * @param {{exp_start_date?: string, exp_end_date?: string}} predecessor
 * @param {{exp_start_date?: string}} successor
 */
export function startsBeforePredecessorEnds(predecessor, successor) {
	const end = taskEndDay(predecessor)
	const start = isoDay(successor?.exp_start_date)
	return Boolean(end && start && start < end)
}
