// Value Add next to Percent Billable in the stop and break dialogs (#1744, parent #1031).
// Value Add is the person's own rating, preset 100. Percent Billable is what the customer is
// billed; it shows on every project (external people may bill internal projects too). The stop
// and break dialogs start at the project's preset (timesheet_utils.percent_billable_preset: the
// project's own value, else 100 for a customer project and 0 for phamos' own, #1896), or at 0
// when there is none. Kept free of DOM/frappe so it runs under vitest.

export const RATING_OPTIONS = [100, 75, 50, 25, 0]
export const VALUE_ADD_DEFAULT = 100
export const PERCENT_BILLABLE_DEFAULT = 0 // same as timesheet_utils.DEFAULT_PERCENT_BILLABLE

// The server's preset ("100", "0", …) as a dialog value; 0 when missing or not an option.
export function percentBillablePreset(value) {
	const n = value === null || value === undefined || value === "" ? NaN : Number(value)
	return RATING_OPTIONS.includes(n) ? n : PERCENT_BILLABLE_DEFAULT
}
export const VALUE_ADD_HELP =
	"How much of this time added value? Was I working the whole time? Would I pay for this work myself? Did I take breaks I didn't track? Was I distracted? Was I at my best?"

// Arguments for stop_timer / create_break_timesheet.
export function ratingArgs(valueAdd, percentBillable) {
	return { value_add: valueAdd, percent_billable: percentBillable }
}
