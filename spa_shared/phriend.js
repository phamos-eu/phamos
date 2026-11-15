// Phriend in the cockpits (#1900): the same ball, screenshot and report flow as in Desk
// (phamos/public/js/phriend/, shared through the @phriend alias), told how a cockpit works.
// Mounted once by CockpitShell, so all six cockpits get it.

import { create_phriend } from "@phriend/index"
import { call, text_of } from "@phriend/request"
import { __ } from "@spa/utils/i18n.js"
import { badgeArgs, pageContext } from "@spa/utils/phriendPage.js"

const COUNT_METHOD = "phamos.phriend.api.count_open_reports"
// Desk's Issue list, filtered to open Phriend reports (the cockpit Issue lists have no
// filter for that yet). "Open" means what the badge counts: not Resolved or Closed.
const REPORTS_URL =
	"/app/issue?status=" +
	encodeURIComponent(JSON.stringify(["not in", ["Resolved", "Closed"]])) +
	"&phriend_type=" +
	encodeURIComponent(JSON.stringify(["is", "set"]))

let instance = null
// failed calls before Phriend is mounted (the first calls of a page), handed over on mount
const early = []

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
	watchFailedRequests()
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
		// every cockpit has IssueDetail (spa_shared/router.js); Desk for a cockpit that one day hasn't
		issue_url: (name) =>
			router.hasRoute("IssueDetail")
				? router.resolve({ name: "IssueDetail", params: { name } }).href
				: `/app/issue/${encodeURIComponent(name)}`,
		count_reports: () => call(COUNT_METHOD, badgeArgs(current()), window.csrf_token),
		open_reports: () => window.open(reportsUrl(current()), "_blank", "noopener"),
		on_route_change: (callback) => router.afterEach(() => callback()),
		// above the buttons the cockpits keep in their bottom right corner ("Today" in My Day)
		start: { right: 24, bottom: 76 },
	})
	early.splice(0).forEach((item) => instance.log.record_failed_request(item))
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
// failed call shows "Report it?" and lands in the report's context. It hands back the app's own
// response and error untouched; only a failed response is cloned to read its message.
// Installed when this module loads (CockpitShell imports it before the app mounts), so the
// first calls of a page are seen too.
function watchFailedRequests() {
	const original = typeof window !== "undefined" && window.fetch
	if (!original || original.__phriend || !boot().phriend?.enabled) return
	const wrapped = async (input, init) => {
		const url = input instanceof Request ? input.url : String(input)
		const isApi = url.includes("/api/")
		try {
			const response = await original(input, init)
			if (isApi && !response.ok) record(url, response).catch(() => {})
			return response
		} catch (error) {
			// an aborted request (typeahead, leaving the page) is not a failure
			if (isApi && error?.name !== "AbortError") {
				save({ url, method: methodOf(url), status: 0, message: String(error?.message || error) })
			}
			throw error
		}
	}
	wrapped.__phriend = true
	window.fetch = wrapped
}

function save(item) {
	if (instance) instance.log.record_failed_request(item)
	else if (early.length < 20) early.push(item)
}

async function record(url, response) {
	let message = response.statusText
	try {
		const body = await response.clone().json()
		message = text_of(body.exception || body._error_message || body.message || "") || message
	} catch (e) {
		// not JSON
	}
	save({ url, method: methodOf(url), status: response.status, message })
}

function methodOf(url) {
	const match = String(url).match(/\/api\/method\/([^?#]+)/)
	return match ? decodeURIComponent(match[1]) : ""
}

watchFailedRequests()
