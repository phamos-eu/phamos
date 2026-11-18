// Phriend in Desk: a little black ball with legs on every Desk page.
// Click it (or press its shortcut, Cmd/Ctrl+P by default): a few optional steps, a screenshot
// to draw on -> an Issue.
//
// The ball, the flow and the capture live in ./phriend/ and are shared with the cockpits
// (phamos/phamos#1898). This file only tells them how Desk works. The flow itself is a
// separate bundle (phriend_flow.bundle.js), loaded on the first hover, so Desk pages don't
// carry html2canvas.

import { create_phriend } from "./phriend/index";
import { text_of } from "./phriend/request";

const REPORT_DOCTYPE = "Issue";
const CLOSED_STATUSES = ["Resolved", "Closed"];
const LIST_VIEWS = ["List", "Report", "Tree", "Kanban", "Calendar", "Gantt", "Dashboard"];

function route() {
	return frappe.get_route() || [];
}

function page_context() {
	const r = route();
	let ref_doctype = null;
	let ref_docname = null;
	let doc = null;

	if (r[0] === "Form" && window.cur_frm && cur_frm.doc) {
		ref_doctype = cur_frm.doctype;
		ref_docname = cur_frm.doc.__islocal ? null : cur_frm.docname;
		doc = {
			docstatus: cur_frm.doc.docstatus,
			is_new: !!cur_frm.doc.__islocal,
			is_dirty: !!cur_frm.is_dirty(),
			workflow_state: cur_frm.doc.workflow_state,
			status: cur_frm.doc.status,
		};
	} else if (LIST_VIEWS.includes(r[0])) {
		ref_doctype = r[1] || null;
	}

	const where = ref_docname
		? `${__(ref_doctype)} ${ref_docname}`
		: ref_doctype
		? `${__(ref_doctype)} (${__(r[0])})`
		: document.title;

	return {
		route: r.join("/"),
		where,
		ref_doctype,
		ref_docname,
		context: {
			app: "Desk",
			user: frappe.session.user,
			lang: frappe.boot.lang,
			site: frappe.boot.sitename,
			versions: { ...(frappe.boot.versions || {}) },
			route: r,
			doc,
		},
	};
}

// Open reports about this record, this list's DocType, or this page.
function badge_filters() {
	const r = route();
	const filters = { phriend_type: ["is", "set"], status: ["not in", CLOSED_STATUSES] };
	if (r[0] === "Form" && r[2]) {
		filters.phriend_ref_doctype = r[1];
		filters.phriend_ref_docname = r[2];
	} else if (r[0] && r[1] && r[0] !== "Workspaces") {
		filters.phriend_ref_doctype = r[1];
	} else {
		filters.phriend_route = r.join("/");
	}
	return filters;
}

function server_message(xhr) {
	try {
		const body = JSON.parse(xhr.responseText || "{}");
		let message = body.exception || body._error_message || body.message;
		if (!message && body._server_messages) {
			message = JSON.parse(body._server_messages)
				.map((m) => {
					try {
						return JSON.parse(m).message;
					} catch (e) {
						return m;
					}
				})
				.join(" | ");
		}
		return message ? text_of(message) : xhr.statusText;
	} catch (e) {
		return xhr.statusText; // not JSON
	}
}

function method_of(data) {
	if (typeof data !== "string") return (data && data.cmd) || "";
	const match = data.match(/(?:^|&)cmd=([^&]+)/);
	return match ? decodeURIComponent(match[1]) : "";
}

// A plain <script> tag, not frappe.require: that greys out the whole page while it loads,
// and this runs when the pointer merely moves over the ball.
function load_flow() {
	if (window.phriend_flow) return Promise.resolve(window.phriend_flow);
	return new Promise((resolve, reject) => {
		const script = document.createElement("script");
		script.src = frappe.assets.bundled_asset("phriend_flow.bundle.js");
		script.onload = () =>
			window.phriend_flow ? resolve(window.phriend_flow) : reject(new Error("phriend_flow missing"));
		script.onerror = () => {
			script.remove();
			reject(new Error(`Could not load ${script.src}`));
		};
		document.head.appendChild(script);
	});
}

// The Implementation Cockpit finds the implementation of the page or record itself (#1671).
function status_url(ctx) {
	const query = new URLSearchParams();
	if (ctx.ref_doctype && ctx.ref_docname) {
		query.set("ref_doctype", ctx.ref_doctype);
		query.set("ref_docname", ctx.ref_docname);
	} else if (ctx.route) {
		query.set("route", ctx.route);
	}
	return `/implementation-cockpit/status?${query}`;
}

const desk = {
	__: (text, args) => __(text, args),
	csrf_token: () => frappe.csrf_token,
	page_context,
	load_flow,
	issue_url: (name) => `/app/issue/${encodeURIComponent(name)}`,
	// with a target system the reports are Issues there; the ones here would mislead
	count_reports: () =>
		frappe.model.can_read(REPORT_DOCTYPE) && !(frappe.boot.phriend && frappe.boot.phriend.has_target)
			? frappe.db.count(REPORT_DOCTYPE, { filters: badge_filters() })
			: Promise.resolve(0),
	// in a new tab, like the cockpits, so a report in progress isn't lost
	open_reports: () => {
		const filters = badge_filters();
		const query = Object.entries(filters)
			.map(([key, value]) => `${key}=${encodeURIComponent(Array.isArray(value) ? JSON.stringify(value) : value)}`)
			.join("&");
		window.open(`/app/issue?${query}`, "_blank", "noopener");
	},
	// the Implementation Cockpit for users who may open it (phamos/phriend/boot.py)
	open_status:
		frappe.boot.phriend && frappe.boot.phriend.implementation_cockpit
			? (ctx) => window.open(status_url(ctx), "_blank", "noopener")
			: null,
	on_route_change: (callback) => {
		if (frappe.router && typeof frappe.router.on === "function") frappe.router.on("change", callback);
		else $(window).on("hashchange popstate", callback);
	},
	// the user's own shortcut, else the site's (Phriend Settings); "" when off
	shortcut: (frappe.boot.phriend && frappe.boot.phriend.shortcut) || "",
	default_shortcut: (frappe.boot.phriend && frappe.boot.phriend.default_shortcut) || "",
	user: frappe.session.user,
};

frappe.provide("phriend");
phriend.instance = create_phriend(desk); // records errors from now on

$(document).ajaxError((event, xhr, settings) => {
	phriend.instance.log.record_failed_request({
		url: settings.url,
		method: method_of(settings.data),
		status: xhr.status,
		message: server_message(xhr),
	});
});

$(document).ready(() => {
	if (!frappe.boot || !frappe.boot.phriend || !frappe.boot.phriend.enabled) return;
	if (frappe.session.user === "Guest") return;
	phriend.instance.mount();
});
