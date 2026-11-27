// Phriend on the website pages (phamos/phamos#2104): the same ball, flow and screenshot as in
// Desk and the cockpits (./phriend/), told how a website page works. Loaded by
// phriend_web.bundle.js, and only after the server said Phriend is for this user
// (window.phriend_web_boot, from phamos.phriend.api.get_web_boot).

import { create_phriend } from "./phriend/index";
import { call, text_of } from "./phriend/request";

const COUNT_METHOD = "phamos.phriend.api.count_open_reports";
// Desk's Issue list, filtered to open Phriend reports, as in the cockpits
const REPORTS_URL =
	"/app/issue?status=" +
	encodeURIComponent(JSON.stringify(["not in", ["Resolved", "Closed"]])) +
	"&phriend_type=" +
	encodeURIComponent(JSON.stringify(["is", "set"]));

const TRANSLATIONS_METHOD = "phamos.phriend.api.get_web_translations";
const MESSAGES_STORE = "phriend:web_messages";

const boot = window.phriend_web_boot || {};
// Phriend's words in the user's language (website pages have no translation table of their own)
let messages = {};
const translate = (text, args) => {
	const own = messages[text] || text;
	return typeof window.__ === "function" ? window.__(own, args) : own;
};

// From the browser while the language and phamos version stay the same, else from the server
// once. English needs none; without them Phriend just speaks English.
async function load_messages() {
	const key = boot.messages_key;
	if (!key) return {};
	try {
		const stored = JSON.parse(localStorage.getItem(MESSAGES_STORE) || "null");
		if (stored && stored.key === key) return stored.messages || {};
	} catch (e) {
		// no storage (private window) or a broken entry: ask the server
	}
	const response = await fetch(`/api/method/${TRANSLATIONS_METHOD}`, {
		credentials: "same-origin",
		headers: { Accept: "application/json" },
	});
	if (!response.ok) return {};
	const loaded = (await response.json()).message || {};
	try {
		localStorage.setItem(MESSAGES_STORE, JSON.stringify({ key, messages: loaded }));
	} catch (e) {
		// full or blocked: fetched again next time
	}
	return loaded;
}

// A website page is its path: no record behind it that Phriend knows of. The query's values
// stay out (search terms, names), its keys are enough (as in the cockpits, GDPR review of !1162).
function page_context() {
	const path = window.location.pathname.replace(/^\/+|\/+$/g, "") || "/";
	const query = [...new URLSearchParams(window.location.search).keys()];
	return {
		route: path.slice(0, 140),
		where: document.title || path,
		ref_doctype: null,
		ref_docname: null,
		context: {
			app: "Website",
			user: boot.user || null,
			lang: boot.lang || null,
			site: (window.frappe && frappe.boot && frappe.boot.sitename) || window.location.host,
			versions: { ...(boot.versions || {}) },
			route: { path: window.location.pathname, query },
		},
	};
}

// The report flow (html2canvas and the drawing tools), Desk's bundle, by its hashed URL.
function load_flow() {
	if (window.phriend_flow) return Promise.resolve(window.phriend_flow);
	const assets = (window.frappe && frappe.boot && frappe.boot.assets_json) || {};
	const src = assets["phriend_flow.bundle.js"];
	if (!src) return Promise.reject(new Error("phriend_flow.bundle.js missing in assets.json"));
	return new Promise((resolve, reject) => {
		const script = document.createElement("script");
		script.src = src;
		script.onload = () =>
			window.phriend_flow ? resolve(window.phriend_flow) : reject(new Error("phriend_flow missing"));
		script.onerror = () => {
			script.remove();
			reject(new Error(`Could not load ${src}`));
		};
		document.head.appendChild(script);
	});
}

function csrf_token() {
	return (window.frappe && frappe.csrf_token) || window.csrf_token || "";
}

function open_status(ctx) {
	const query = new URLSearchParams();
	if (ctx.issue) query.set("issue", ctx.issue);
	else if (ctx.route) query.set("route", ctx.route);
	window.open(`/implementation-cockpit/status?${query}`, "_blank", "noopener");
}

const instance = create_phriend({
	__: translate,
	csrf_token,
	page_context,
	load_flow,
	issue_url: (name) => `/app/issue/${encodeURIComponent(name)}`,
	// with a target system the reports are Issues there; the ones here would mislead
	count_reports: () =>
		boot.has_target ? Promise.resolve(0) : call(COUNT_METHOD, { route: page_context().route }, csrf_token()),
	open_reports: () =>
		window.open(`${REPORTS_URL}&phriend_route=${encodeURIComponent(page_context().route)}`, "_blank", "noopener"),
	open_status: boot.implementation_cockpit ? open_status : null,
	// every website page is a page load of its own
	on_route_change: null,
	shortcut: boot.shortcut || "",
	default_shortcut: boot.default_shortcut || "",
	user: boot.user || "",
	features: boot.features || {},
	quiet: boot.quiet || null,
	can_configure: !!boot.can_configure,
	open_settings: () => window.open("/app/phriend-settings", "_blank", "noopener"),
	voice: boot.voice || null,
	// no realtime socket on the website (#2012 stays Desk and cockpits)
	on_event: null,
});

window.phriend = Object.assign(window.phriend || {}, { instance });

// failed calls of the page (frappe.call uses jQuery here too) show "Report it?", as in Desk
if (window.jQuery) {
	jQuery(document).ajaxError((event, xhr, settings) => {
		let message = xhr.statusText;
		try {
			const body = JSON.parse(xhr.responseText || "{}");
			message = text_of(body.exception || body._error_message || body.message || "") || message;
		} catch (e) {
			// not JSON
		}
		const data = typeof settings.data === "string" ? settings.data : "";
		const match = data.match(/(?:^|&)cmd=([^&]+)/);
		instance.log.record_failed_request({
			url: settings.url,
			method: match ? decodeURIComponent(match[1]) : "",
			status: xhr.status,
			message,
		});
	});
}

load_messages()
	.catch(() => ({}))
	.then((loaded) => {
		messages = loaded;
		instance.mount();
	});
