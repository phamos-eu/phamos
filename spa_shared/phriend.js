// Phriend in the cockpits (#1900): the same ball, screenshot and report flow as in Desk
// (phamos/public/js/phriend/, shared through the @phriend alias), told how a cockpit works.
// Mounted once by CockpitShell, so all six cockpits get it.

import { create_phriend } from "@phriend/index"
import { call, text_of } from "@phriend/request"
import { __ } from "@spa/utils/i18n.js"
import { badgeArgs, pageContext } from "@spa/utils/phriendPage.js"

const COUNT_METHOD = "phamos.phriend.api.count_open_reports"
// Desk's Issue list, filtered to open Phriend reports (the cockpit Issue lists have no
// filter for that yet)
const REPORTS_URL = "/app/issue?status=Open&phriend_type=%5B%22is%22%2C%22set%22%5D"

let instance = null

function boot() {
	return (typeof window !== "undefined" && window.frappe?.boot) || {}
}

/**
 * Start Phriend in this cockpit, once. Errors are recorded from here on; the ball shows when
 * the cockpit boot says Phriend is for this user (phamos/www/spa_boot.py).
 * @param {object} router  the cockpit's vue-router
 * @param {() => string} heading  the page heading the shell shows, for "Reported on"
 */
export function mountPhriend(router, heading) {
	if (instance || !boot().phriend?.enabled) return
	const current = () =>
		pageContext(
			router.currentRoute.value,
			{ base: router.options.history.base, cockpit: document.title, heading: heading() },
			__
		)

	instance = create_phriend({
		__,
		csrf_token: () => window.csrf_token || boot().csrf_token,
		page_context: () => {
			const ctx = current()
			const b = boot()
			ctx.context = {
				...ctx.context,
				user: b.user?.name,
				lang: b.lang,
				site: b.site_name,
				versions: { ...(b.versions || {}) },
			}
			return ctx
		},
		load_flow: () => import("@phriend/flow"),
		issue_url: (name) => router.resolve({ name: "IssueDetail", params: { name } }).href,
		count_reports: () => call(COUNT_METHOD, badgeArgs(current()), window.csrf_token),
		open_reports: () => window.open(reportsUrl(current()), "_blank", "noopener"),
		on_route_change: (callback) => router.afterEach(() => callback()),
		// above the buttons the cockpits keep in their bottom right corner ("Today" in My Day)
		start: { right: 24, bottom: 76 },
	})
	watchFailedRequests(instance)
	instance.mount()
}

function reportsUrl(ctx) {
	const extra = ctx.ref_doctype
		? `&phriend_ref_doctype=${encodeURIComponent(ctx.ref_doctype)}` +
			(ctx.ref_docname ? `&phriend_ref_docname=${encodeURIComponent(ctx.ref_docname)}` : "")
		: `&phriend_route=${encodeURIComponent(ctx.route)}`
	return REPORTS_URL + extra
}

// The cockpits call the server with fetch (frappe-ui's resources, keepaliveCall). Desk reports
// failed calls through jQuery's ajaxError; here a thin wrapper around fetch does the same, so a
// failed call shows "Report it?" and lands in the report's context.
function watchFailedRequests(phriend) {
	const original = window.fetch
	if (!original || original.__phriend) return
	const wrapped = async (input, init) => {
		const url = typeof input === "string" ? input : input?.url || ""
		const isApi = url.includes("/api/")
		try {
			const response = await original(input, init)
			if (isApi && !response.ok) record(phriend, url, response)
			return response
		} catch (error) {
			if (isApi) phriend.log.record_failed_request({ url, method: methodOf(url), status: 0, message: String(error?.message || error) })
			throw error
		}
	}
	wrapped.__phriend = true
	window.fetch = wrapped
}

async function record(phriend, url, response) {
	let message = response.statusText
	try {
		const body = await response.clone().json()
		message = text_of(body.exception || body._error_message || body.message || "") || message
	} catch (e) {
		// not JSON
	}
	phriend.log.record_failed_request({ url, method: methodOf(url), status: response.status, message })
}

function methodOf(url) {
	const match = String(url).match(/\/api\/method\/([^?#]+)/)
	return match ? decodeURIComponent(match[1]) : ""
}
