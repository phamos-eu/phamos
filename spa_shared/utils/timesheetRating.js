// Value Add next to Percent Billable in the timer dialogs (#1743, parent #1031).
// Value Add is the person's own rating, preset 100. Percent Billable is what the customer is
// billed; it shows on every project and is preset from the project, 100 when the project has none.
// Values are strings, as the Select fields on the Timesheet Record store them.

export const VALUE_ADD_DEFAULT = "100"
export const VALUE_ADD_HELP =
	"How much of this time added value? Was I working the whole time? Would I pay for this work myself? Did I take breaks I didn't track? Was I distracted? Was I at my best?"

export function ratingOptions() {
	return ["100", "75", "50", "25", "0"].map((value) => ({ label: `${value} %`, value }))
}

export function billablePreset(projectValue) {
	return projectValue === undefined || projectValue === null || projectValue === "" ? "100" : String(projectValue)
}
