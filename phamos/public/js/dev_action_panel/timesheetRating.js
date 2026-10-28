// Value Add next to Percent Billable in the stop and break dialogs (#1744, parent #1031).
// Value Add is the person's own rating and always asked. Percent Billable only counts on
// billable projects (an Implementation, not internal); elsewhere the server stores 0, so the
// dialogs hide it and don't send it. Kept free of DOM/frappe so it runs under vitest.

export const RATING_OPTIONS = [100, 75, 50, 25, 0]
export const VALUE_ADD_DEFAULT = 100
export const VALUE_ADD_HELP =
	"How much of this time added value? Was I working the whole time? Would I pay for this work myself? Did I take breaks I didn't track? Was I distracted? Was I at my best?"

// `context` is a project row ({is_billable, percent_billable}) or a timer session
// ({project_is_billable, project_percent_billable}).
export function showBillable(context) {
	return Boolean(context?.is_billable ?? context?.project_is_billable)
}

export function billablePreset(context) {
	if (!showBillable(context)) return 0
	const value = context.percent_billable ?? context.project_percent_billable
	return value === undefined || value === null || value === "" ? 100 : Number(value)
}

// Arguments for stop_timer / create_break_timesheet; percentBillable is null when it was hidden.
export function ratingArgs(valueAdd, percentBillable) {
	const args = { value_add: valueAdd }
	if (percentBillable !== null && percentBillable !== undefined) args.percent_billable = percentBillable
	return args
}
