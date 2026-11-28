// The Phriend report on the cockpit Issue page (#1901): labels and the one-line summary of the
// technical details. Pure, so it can be tested without a browser.
import { __ } from "./i18n.js"

// What the reporter picked in Phriend; "Other" is "Something else" there too.
const TYPE_LABELS = { Bug: "Bug", Improvement: "Improvement", Question: "Question", Other: "Something else" }

export function typeLabel(type) {
	return __(TYPE_LABELS[type] || type || "")
}

export function typeTheme(type) {
	return { Bug: "red", Improvement: "blue", Question: "orange" }[type] || "gray"
}

function count(n, one, many) {
	return n === 1 ? __(one) : __(many, [n])
}

/** "Chrome 156, macOS · 1440x900 @1x · phamos 15.140.0 · 2 errors · 1 failed request" */
export function detailsSummary(details = {}) {
	const parts = []
	if (details.browser) parts.push(details.browser)
	if (details.viewport) parts.push(details.viewport)
	const phamos = (details.versions || {}).phamos
	if (phamos) parts.push(`phamos ${phamos}`)
	const errors = (details.recent_errors || []).length
	const failed = (details.failed_requests || []).length
	if (errors) parts.push(count(errors, "1 error", "{0} errors"))
	if (failed) parts.push(count(failed, "1 failed request", "{0} failed requests"))
	if (!errors && !failed) parts.push(__("no errors"))
	return parts.join(" · ")
}

/** One line per error or failed request: "500 GET /api/method/x: Server Error" */
export function entryLine(entry = {}) {
	const head = [entry.status, entry.method, entry.url || entry.source].filter(Boolean).join(" ")
	const message = entry.message || entry.type || ""
	return head && message ? `${head}: ${message}` : head || message
}

/** "erpnext 15.119.3, frappe 15.118.0, …", phamos first */
export function versionsLine(versions = {}) {
	return Object.entries(versions)
		.filter(([, v]) => v)
		.sort(([a], [b]) => (a === "phamos" ? -1 : b === "phamos" ? 1 : a.localeCompare(b)))
		.map(([app, v]) => `${app} ${v}`)
		.join(", ")
}
