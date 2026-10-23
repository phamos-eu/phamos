// Timesheets of the open implementation (#1685): filters, rows and the summary.
// The view keeps the filters in the URL query, so links (report emails, #1687) open a filtered view.
import { reactive } from "vue"
import { call } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"
import spaConfig from "./config"

export const PAGE_SIZES = [20, 50, 100, 500]

export const sheets = reactive({
	implementation: null,
	projects: [],
	defaults: { from: "", to: "" },
	filters: { from: "", to: "", project: "", group: "month" },
	sort: { by: "start_date", order: "desc" },
	pageLength: 20,
	rows: [],
	total: 0,
	summary: null,
	loading: false,
	error: "",
})

let requestId = 0

/** Load the project list and defaults when the implementation changes. */
export async function initTimesheets(implementation, query = {}) {
	if (sheets.implementation !== implementation) {
		sheets.implementation = implementation
		sheets.projects = []
		sheets.rows = []
		sheets.summary = null
		const data = await call(`${spaConfig.api}.get_timesheet_filters`, { implementation })
		sheets.projects = data?.projects || []
		sheets.defaults = { from: data?.default_from || "", to: data?.default_to || "" }
	}
	sheets.filters = {
		from: query.from ?? sheets.defaults.from,
		to: query.to ?? sheets.defaults.to,
		project: query.project || "",
		group: query.group === "week" ? "week" : "month",
	}
	return reloadTimesheets()
}

function params() {
	return {
		implementation: sheets.implementation,
		from_date: sheets.filters.from || null,
		to_date: sheets.filters.to || null,
		project: sheets.filters.project || null,
		sort_by: sheets.sort.by,
		sort_order: sheets.sort.order,
	}
}

/** Reload rows (first page) and summary for the current filters. */
export async function reloadTimesheets() {
	const id = ++requestId
	sheets.loading = true
	sheets.error = ""
	try {
		const [list, summary] = await Promise.all([
			call(`${spaConfig.api}.get_timesheets`, { ...params(), start: 0, page_length: sheets.pageLength }),
			call(`${spaConfig.api}.get_timesheet_summary`, { ...params(), group_by: sheets.filters.group }),
		])
		if (id !== requestId) return
		sheets.rows = list?.timesheets || []
		sheets.total = list?.total || 0
		sheets.summary = summary
	} catch (e) {
		if (id === requestId) sheets.error = e?.message || __("Could not load the timesheets")
	} finally {
		if (id === requestId) sheets.loading = false
	}
}

export async function loadMoreTimesheets() {
	const list = await call(`${spaConfig.api}.get_timesheets`, {
		...params(),
		start: sheets.rows.length,
		page_length: sheets.pageLength,
	})
	sheets.rows = [...sheets.rows, ...(list?.timesheets || [])]
	sheets.total = list?.total ?? sheets.total
}

export function exportTimesheets() {
	return call(`${spaConfig.api}.export_timesheets`, params())
}

export async function giveFeedback(timesheet, rating, comment) {
	const saved = await call(`${spaConfig.api}.set_timesheet_feedback`, {
		implementation: sheets.implementation,
		timesheet,
		rating,
		comment,
	})
	const row = sheets.rows.find((r) => r.name === timesheet)
	if (row) Object.assign(row, { custom_rating: saved.custom_rating, customer_comment: saved.customer_comment })
	return saved
}
