// Percent Billable in the stop and break dialogs. They start at the project's preset
// (timesheet_utils.percent_billable_preset: the project's own value, else 100 for a customer
// project and 0 for phamos' own, #1896), or at 0 when there is none. Kept free of DOM/frappe so
// it runs under vitest.
// version-15 adaptation: Value Add (#1744) is not released here, so only Percent Billable.

export const RATING_OPTIONS = [100, 75, 50, 25, 0]
export const PERCENT_BILLABLE_DEFAULT = 0 // same as timesheet_utils.DEFAULT_PERCENT_BILLABLE

// The server's preset ("100", "0", …) as a dialog value; 0 when missing or not an option.
export function percentBillablePreset(value) {
	const n = value === null || value === undefined || value === "" ? NaN : Number(value)
	return RATING_OPTIONS.includes(n) ? n : PERCENT_BILLABLE_DEFAULT
}
