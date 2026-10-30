/**
 * Defaults and checks of the "New Task" dialog (#1752), kept free of Vue so they are
 * unit-tested. The server (department_cockpit.create_task) checks the same rules.
 */

export const DEFAULT_ESTIMATE_HOURS = 1
const DEFAULT_PRIORITY = "Medium"

/**
 * A fresh form: start and end today, the current user as Task Owner, 1 hour, Medium,
 * and the cockpit's project from phamos Settings (none in the personal cockpit).
 */
export function newTaskDefaults({ subject = "", today, user = "", options = {}, projectField = "" }) {
	const priorities = options.task_priorities || []
	return {
		subject: subject.trim(),
		exp_start_date: today,
		exp_end_date: today,
		custom_task_owner: user || "",
		expected_time: DEFAULT_ESTIMATE_HOURS,
		priority: priorities.includes(DEFAULT_PRIORITY) ? DEFAULT_PRIORITY : priorities[0] || "",
		project: (projectField && options[projectField]) || "",
		task_type: "",
		description: "",
	}
}

/** A start date after the end pulls the end along, so the range stays valid. */
export function withStartDate(form, start) {
	const end = form.exp_end_date && start && form.exp_end_date < start ? start : form.exp_end_date
	return { ...form, exp_start_date: start, exp_end_date: end }
}

/**
 * Hours as typed into the estimate: a decimal number with a dot or a comma
 * ("2.5" and "2,5" are both two and a half hours). NaN when it isn't a number.
 */
export function parseHours(value) {
	if (typeof value === "number") return value
	const text = String(value ?? "").trim().replace(",", ".")
	return /^\d*\.?\d+$|^\d+\.$/.test(text) ? Number(text) : NaN
}

/** One message per problem, in field order; empty when the form can be saved. */
export function newTaskErrors(form) {
	const errors = []
	if (!String(form.subject || "").trim()) errors.push("Subject is required")
	if (!form.exp_start_date) errors.push("Expected start is required")
	if (!form.exp_end_date) errors.push("Expected end is required")
	if (form.exp_start_date && form.exp_end_date && form.exp_end_date < form.exp_start_date) {
		errors.push("Expected end date cannot be before start date")
	}
	if (!form.custom_task_owner) errors.push("Task Owner is required")
	if (!(parseHours(form.expected_time) > 0)) {
		errors.push("Estimated time must be a number of hours above 0, e.g. 2.5")
	}
	if (!form.priority) errors.push("Priority is required")
	return errors
}

/**
 * Who can be Task Owner (#1751): enabled System Users, as the server checks.
 * One shared object: FrappeLink watches its filters deeply, so an inline literal
 * (a new object on every render) would reload the user search over and over.
 */
export const TASK_OWNER_FILTERS = Object.freeze({ enabled: 1, user_type: "System User" })
