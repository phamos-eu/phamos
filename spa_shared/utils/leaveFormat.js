// My Leave in the Personal Cockpit (phamos/phamos#1714): pure helpers, kept free of Vue and the
// DOM so Vitest can run them.

export const LEAVE_STATUSES = ["Open", "Approved", "Rejected", "Cancelled"]

const STATUS_THEMES = { Open: "orange", Approved: "green", Rejected: "red", Cancelled: "gray" }

/** frappe-ui Badge theme for a Leave Application status. */
export function leaveStatusTheme(status) {
	return STATUS_THEMES[status] || "gray"
}

/** Days as a short number: 3, 2.5, 0.5; never "3.0". */
export function formatLeaveDays(value) {
	const n = Number(value)
	if (!Number.isFinite(n)) return "0"
	return String(Math.round(n * 100) / 100)
}

/** True when a leave starts and ends on the same day. */
export function isSingleDay(leave) {
	return Boolean(leave?.from_date) && leave.from_date === leave.to_date
}

/**
 * Calendar badge for a leave row (from Phase 2's Event): an i18n key and a theme, or null.
 * @param {{state?: string, error?: string}} calendar
 */
export function calendarBadge(calendar) {
	switch (calendar?.state) {
		case "synced":
			return { key: "In my calendar", theme: "green", title: "" }
		case "pending":
			return { key: "Being added to my calendar", theme: "blue", title: "" }
		case "error":
			return { key: "Not in my calendar", theme: "orange", title: calendar.error || "" }
		default:
			return null
	}
}

/**
 * Check the Apply dialog before it is sent. Returns an i18n key for the first problem, or "".
 * HRMS still validates balance, overlap and block days on the server.
 */
export function leaveFormError(form) {
	if (!form?.leave_type) return "Choose a leave type."
	if (!form.from_date || !form.to_date) return "Choose from and to dates."
	if (form.to_date < form.from_date) return "The to date is before the from date."
	if (form.half_day) {
		if (form.from_date !== form.to_date) {
			if (!form.half_day_date) return "Choose the half day."
			if (form.half_day_date < form.from_date || form.half_day_date > form.to_date) {
				return "The half day must lie within the leave."
			}
		}
	}
	return ""
}

/** The payload the backend expects, with the half day date filled in for a one-day leave. */
export function leavePayload(form) {
	const halfDay = form.half_day ? 1 : 0
	return {
		leave_type: form.leave_type,
		from_date: form.from_date,
		to_date: form.to_date,
		half_day: halfDay,
		half_day_date: halfDay ? form.half_day_date || form.from_date : null,
		description: (form.description || "").trim() || null,
		cover_employee: form.cover_employee || null,
	}
}
