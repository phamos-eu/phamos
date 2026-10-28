// Value Add next to Percent Billable in the stop and break dialogs (#1744, parent #1031).
// Value Add is the person's own rating, preset 100. Percent Billable is what the customer is
// billed; it shows on every project (external people may bill internal projects too) and is
// preset from the project, 100 when the project has none. Kept free of DOM/frappe so it runs under vitest.

export const RATING_OPTIONS = [100, 75, 50, 25, 0]
export const VALUE_ADD_DEFAULT = 100
export const VALUE_ADD_HELP =
	"How much of this time added value? Was I working the whole time? Would I pay for this work myself? Did I take breaks I didn't track? Was I distracted? Was I at my best?"

// `context` is a project row ({percent_billable}), a timer session ({project_percent_billable})
// or the answer of get_billing_context ({percent_billable}).
export function billablePreset(context) {
	const value = context?.percent_billable ?? context?.project_percent_billable
	return value === undefined || value === null || value === "" ? 100 : Number(value)
}

// Arguments for stop_timer / create_break_timesheet.
export function ratingArgs(valueAdd, percentBillable) {
	return { value_add: valueAdd, percent_billable: percentBillable }
}
