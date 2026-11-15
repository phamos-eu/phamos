// Phriend's controller, shared by Desk (phriend.bundle.js) and the cockpits (spa_shared).
// The host supplies what differs between them:
//
//   __(text, args)            translate
//   csrf_token()              for the server calls
//   page_context()            { route, page_url, page_title, where, ref_doctype, ref_docname, context }
//   load_flow()               Promise of the report flow module (flow.js), loaded on demand
//   issue_url(name)           where "Saved as ISS-…" links to
//   count_reports()           optional: Promise of the open reports for this page (the badge)
//   open_reports()            optional: show those reports
//   on_route_change(cb)       optional
//   add_shortcut(cb)          optional: Ctrl+Shift+B the host's way; default is a keydown listener

import { Ball } from "./ball";
import { ErrorLog } from "./errors";
import { DRAFT_KEY, escape_html, storage_get, storage_set } from "./util";

export { DRAFT_KEY };
const GREETED_KEY = "phriend:greeted";

export function create_phriend(host) {
	return new Phriend(host);
}

class Phriend {
	constructor(host) {
		this.host = host;
		this.__ = host.__;
		this.open = false;
		this.log = new ErrorLog(); // start recording errors as early as possible
		this.log.on_failed_request((item) => this.on_failed_request(item));
	}

	mount() {
		if (this.ball || document.getElementById("phriend-root")) return;
		const __ = this.__;
		this.ball = new Ball({
			label: __("Phriend: report a problem (Ctrl+Shift+B)"),
			on_click: () => this.report(),
			on_badge_click: () => this.host.open_reports && this.host.open_reports(),
			on_first_interest: () => this.load_flow().catch(() => {}),
		});

		if (this.host.add_shortcut) {
			this.host.add_shortcut(() => this.report());
		} else {
			document.addEventListener("keydown", (e) => {
				if (e.ctrlKey && e.shiftKey && !e.altKey && (e.key === "B" || e.key === "b")) {
					e.preventDefault();
					this.report();
				}
			});
		}
		if (this.host.on_route_change) this.host.on_route_change(() => this.refresh_badge());

		if (storage_get(DRAFT_KEY, "session")) {
			this.ball.set_pending(true);
			this.ball.say(
				`${escape_html(__("You have a report that wasn't sent."))} <button type="button" class="link" data-open>${escape_html(__("Open it"))}</button>`,
				10000
			);
			this.bind_bubble_link("[data-open]", () => this.report(this.saved_draft()));
		} else if (!storage_get(GREETED_KEY)) {
			this.ball.say(escape_html(__("Hi, I'm Phriend! Click me when something looks wrong.")), 6000);
			storage_set(GREETED_KEY, "1");
		}
		this.refresh_badge();
	}

	bind_bubble_link(selector, callback) {
		const link = this.ball.bubble.querySelector(selector);
		if (link) link.addEventListener("click", callback);
	}

	saved_draft() {
		try {
			return JSON.parse(storage_get(DRAFT_KEY, "session") || "null");
		} catch (e) {
			return null;
		}
	}

	load_flow() {
		if (!this._flow) {
			this._flow = Promise.resolve(this.host.load_flow()).catch((e) => {
				this._flow = null; // try again next time
				throw e;
			});
		}
		return this._flow;
	}

	// Everything we know about the page right now: what the host adds plus the browser.
	context() {
		const page = this.host.page_context() || {};
		return {
			...page,
			page_url: page.page_url || window.location.href,
			page_title: page.page_title || document.title,
			context: {
				captured_at: new Date().toISOString(),
				...(page.context || {}),
				viewport: `${window.innerWidth}x${window.innerHeight} @${window.devicePixelRatio}x`,
				user_agent: navigator.userAgent,
				...this.log.snapshot(),
			},
		};
	}

	async report(draft = null) {
		if (this.open || !this.ball) return;
		const sender = this.sender;
		if (sender && sender.sending) {
			this.ball.say(escape_html(this.__("Still sending your last report…")), 3000);
			return;
		}
		if (sender && sender.failed && !draft) {
			// the ball reopens the report that didn't go out, with its own screenshot
			const failed = sender.failed.report;
			draft = { ...failed.draft, canvas: failed.canvas, from_failed: true };
		}
		this.open = true;
		this.ball.hop();
		const ctx = this.context(); // before anything changes on the page
		const slow = setTimeout(() => this.ball.say(escape_html(this.__("One moment…")), 0), 150);
		let flow;
		try {
			flow = await this.load_flow();
		} catch (e) {
			console.warn("Phriend: could not load the report flow", e);
			this.open = false;
			this.ball.say(escape_html(this.__("Phriend couldn't start. Reload the page and try again.")), 6000);
			return;
		} finally {
			clearTimeout(slow);
		}
		this.ball.hide_bubble();
		try {
			flow.open_report({ phriend: this, ctx, draft, on_close: () => (this.open = false) });
		} catch (e) {
			console.error("Phriend: the report flow failed to open", e);
			this.open = false;
			this.ball.set_away(false);
		}
	}

	on_failed_request(item) {
		if (!this.ball || this.open || !(item.status >= 500)) return;
		if (this.sender && this.sender.busy()) return; // keep "Sending…" / "Try again" in the bubble
		this.ball.say(
			`${escape_html(this.__("Whoops, that call failed."))} <button type="button" class="link" data-report>${escape_html(this.__("Report it?"))}</button>`,
			6000
		);
		this.bind_bubble_link("[data-report]", () => this.report());
	}

	refresh_badge() {
		if (!this.host.count_reports || !this.ball) return;
		clearTimeout(this._badge_timer);
		this._badge_timer = setTimeout(() => {
			Promise.resolve(this.host.count_reports())
				.then((count) =>
					this.ball.set_badge(count, this.__("{0} open Phriend reports for this page", [count || 0]))
				)
				.catch(() => {});
		}, 400);
	}
}
