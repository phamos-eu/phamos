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
//   open_status(ctx)          optional: where the reports about this place (or ctx.issue) stand, in the Implementation Cockpit
//   on_route_change(cb)       optional
//   shortcut                  the user's shortcut ("Mod+P"; "" when off)
//   default_shortcut          the site's (Phriend Settings), for "Back to the default"
//   start                     optional: { right, bottom } where the ball sits until it is dragged
//   user                      the logged-in user, so an unsent draft is offered only to them

import { Ball } from "./ball";
import { ErrorLog } from "./errors";
import * as nudge from "./nudge";
import { format, matches, parse } from "./shortcut";
import { DRAFT_KEY, browser_name, escape_html, storage_get, storage_set } from "./util";

export { DRAFT_KEY };
const GREETED_KEY = "phriend:greeted";
const NUDGE_DELAY = 4000; // after the page (or the tab) shows
const NUDGE_CHECK = 30 * 60 * 1000; // Desk tabs stay open all day
const NUDGE_MS = 8000;

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
		this.recording = false; // the flow is taking a new shortcut: keys are for it
		this.set_shortcut(host.shortcut || "");
	}

	// The user's shortcut, as Phriend Settings and the user's own choice give it ("" when off).
	set_shortcut(text) {
		this.shortcut = text || "";
		this.shortcut_spec = parse(this.shortcut);
		if (this.ball) {
			this.ball.set_label(this.label());
			this.ball.set_keys(format(this.shortcut));
		}
	}

	label() {
		const keys = format(this.shortcut);
		return keys ? this.__("Phriend: report a problem ({0})", [keys]) : this.__("Phriend: report a problem");
	}

	// Before the page and the browser see the key (capture on window): the default, Cmd/Ctrl+P,
	// would otherwise open the print dialog, and Desk prints the form on Ctrl+P.
	listen_for_shortcut() {
		window.addEventListener(
			"keydown",
			(e) => {
				// not while an input method composes a character (Japanese, Chinese…)
				if (this.recording || e.repeat || e.isComposing || e.keyCode === 229) return;
				if (!matches(e, this.shortcut_spec)) return;
				e.preventDefault();
				if (this.open) return; // already open; just don't print
				e.stopPropagation();
				this.report();
			},
			true
		);
	}

	mount() {
		if (this.ball || document.getElementById("phriend-root")) return;
		const __ = this.__;
		this.ball = new Ball({
			label: this.label(),
			on_click: () => this.report(),
			// the number on the ball answers "where do the reports here stand?": the Implementation
			// Cockpit for users who may open it (#1671), else the host's list of those reports
			on_badge_click: () =>
				this.host.open_status
					? this.host.open_status(this.host.page_context() || {})
					: this.host.open_reports && this.host.open_reports(),
			on_first_interest: () => this.load_flow().catch(() => {}),
			start: this.host.start,
			close_label: __("Close"),
		});
		this.ball.set_keys(format(this.shortcut));

		this.listen_for_shortcut();
		if (this.host.on_route_change) this.host.on_route_change(() => this.refresh_badge());

		if (this.saved_draft()) {
			this.ball.set_pending(true);
			this.ball.say(
				`${escape_html(__("You have a report that wasn't sent."))} <button type="button" class="link" data-open>${escape_html(__("Open it"))}</button>`,
				10000,
				"point_up"
			);
			this.bind_bubble_link("[data-open]", () => this.report(this.saved_draft()));
		} else if (!storage_get(GREETED_KEY)) {
			this.ball.say(escape_html(__("Hi, I'm Phriend! Click me when something looks wrong.")), NUDGE_MS, "wave");
			storage_set(GREETED_KEY, "1");
			nudge.write(nudge.after_nudge(nudge.read(this.host.user), Date.now())); // the first nudge
		}
		this.refresh_badge();
		this.start_nudging();
	}

	// "Click me!" now and then, to users who never opened Phriend or not for a while (nudge.js).
	start_nudging() {
		// one pending check: clicking through pages quickly doesn't pile up timers
		const later = () => {
			clearTimeout(this._nudge_timer);
			this._nudge_timer = setTimeout(() => this.maybe_nudge(), NUDGE_DELAY);
		};
		later();
		setInterval(() => this.maybe_nudge(), NUDGE_CHECK);
		document.addEventListener("visibilitychange", () => !document.hidden && later());
		if (this.host.on_route_change) this.host.on_route_change(later);
	}

	maybe_nudge() {
		// never in the way: not over another bubble, an open flow or a report still to send
		if (!this.ball || this.open || document.hidden || this.ball.bubble_showing()) return;
		if ((this.sender && this.sender.busy()) || this.saved_draft()) return;
		const state = nudge.read(this.host.user);
		const now = Date.now();
		if (!nudge.is_due(state, now)) return;
		this.ball.say(
			`<button type="button" class="link" data-nudge>${escape_html(this.__("Click me!"))}</button>`,
			NUDGE_MS,
			"wave"
		);
		this.bind_bubble_link("[data-nudge]", () => this.report());
		nudge.write(nudge.after_nudge(state, now));
	}

	bind_bubble_link(selector, callback) {
		const link = this.ball.bubble.querySelector(selector);
		if (link) link.addEventListener("click", callback);
	}

	saved_draft() {
		try {
			const draft = JSON.parse(storage_get(DRAFT_KEY, "session") || "null");
			// only for the user who wrote it: someone else may log in in the same tab
			if (draft && draft.user !== this.host.user) {
				storage_set(DRAFT_KEY, null, "session");
				return null;
			}
			return draft;
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
				// browser and system, not the full user agent (GDPR review of !1162)
				browser: browser_name(navigator.userAgent),
				...this.log.snapshot(),
			},
		};
	}

	async report(draft = null) {
		if (this.open || !this.ball) return;
		const sender = this.sender;
		if (sender && sender.sending) {
			this.ball.say(escape_html(this.__("Still sending your last report…")), 3000, "fingers_crossed");
			return;
		}
		if (sender && sender.failed && !draft) {
			// the ball reopens the report that didn't go out, with its own screenshot
			const failed = sender.failed.report;
			draft = { ...failed.draft, canvas: failed.canvas, from_failed: true };
		}
		this.open = true;
		// opened: no "Click me!" for the next 10 to 20 days
		nudge.write(nudge.after_click(nudge.read(this.host.user), Date.now()));
		this.ball.hop();
		const ctx = this.context(); // before anything changes on the page
		const slow = setTimeout(() => this.ball.say(escape_html(this.__("One moment…")), 0, "wait"), 150);
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
			6000,
			"point"
		);
		this.bind_bubble_link("[data-report]", () => this.report());
	}

	refresh_badge() {
		if (!this.host.count_reports || !this.ball) return;
		clearTimeout(this._badge_timer);
		this._badge_timer = setTimeout(() => {
			Promise.resolve(this.host.count_reports())
				.then((count) =>
					this.ball.set_badge(
						count,
						this.host.open_status
							? this.__("{0} open reports here. Click to see where they stand", [count || 0])
							: this.__("{0} open Phriend reports for this page", [count || 0])
					)
				)
				.catch(() => {});
		}, 400);
	}
}
