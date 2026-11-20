// Sends a report in the background: the flow is already closed, the ball reports back.
// One report at a time is "unsent": while it is being sent, or after it failed, clicking the
// ball reopens it instead of starting a new one (index.js). Its text stays in sessionStorage
// until it is sent or discarded, so a reload loses no words; its screenshot stays in memory.

import { RequestError, call } from "./request";
import { DRAFT_KEY, escape_html, storage_set } from "./util";

const METHOD = "phamos.phriend.api.create_report";

export class Sender {
	constructor(phriend) {
		this.phriend = phriend;
		this.sending = null; // the report on its way
		this.failed = null; // { report, error }
		window.addEventListener("online", () => this.failed && this.failed.error.kind === "offline" && this.retry());
	}

	busy() {
		return !!(this.sending || this.failed);
	}

	// report: { draft: {title, comment, report_type, priority}, args: () => Promise<args>, canvas }
	async send(report) {
		const { ball, host, __ } = this.phriend;
		storage_set(DRAFT_KEY, JSON.stringify({ ...report.draft, user: host.user }), "session");
		this.failed = null;
		this.sending = report;
		ball.set_pending(true);
		ball.set_busy(true);
		ball.say(escape_html(__("Sending…")), 0, "fingers_crossed");
		try {
			const args = report.args_value || (report.args_value = await report.args());
			const result = await call(METHOD, args, host.csrf_token());
			if (!result || !result.name) throw new RequestError("server", __("unexpected answer from the server"));
			this.sending = null;
			storage_set(DRAFT_KEY, null, "session");
			ball.set_pending(false);
			ball.hop();
			// a system with a target system sends the report there and gets that Issue's address back
			const url = result.url || host.issue_url(result.name);
			// follow it where its status is shown, for users who may open the Implementation Cockpit (#1671)
			const follow =
				host.open_status && !result.url
					? ` · <button type="button" class="link" data-follow>${escape_html(__("Follow its status"))}</button>`
					: "";
			ball.say(
				`${escape_html(__("Got it! Saved as"))} <a href="${escape_html(url)}" target="_blank" rel="noopener" data-issue>${escape_html(result.name)}</a>${follow}`,
				follow ? 12000 : 8000,
				"thumbs_up"
			);
			if (follow) this.phriend.bind_bubble_link("[data-follow]", () => host.open_status({ issue: result.name }));
			this.phriend.refresh_badge();
		} catch (error) {
			const e = error instanceof RequestError ? error : new RequestError("server", error && error.message);
			console.warn("Phriend: sending failed", error);
			this.sending = null;
			this.failed = { report, error: e };
			// a closed flow may have cleared it
			storage_set(DRAFT_KEY, JSON.stringify({ ...report.draft, user: this.phriend.host.user }), "session");
			ball.set_pending(true);
			this.show_failure(e);
		} finally {
			ball.set_busy(false);
		}
	}

	// Give up on a report that can't go out (e.g. not allowed): forget it and its draft.
	discard() {
		this.failed = null;
		storage_set(DRAFT_KEY, null, "session");
		this.phriend.ball.set_pending(false);
		this.phriend.ball.hide_bubble();
	}

	retry() {
		if (this.failed && !this.sending) this.send(this.failed.report);
	}

	// Reopen the failed report in the flow, with its text and its original screenshot.
	edit() {
		if (!this.failed || this.phriend.open) return;
		this.phriend.ball.hide_bubble();
		this.phriend.report();
	}

	show_failure(error) {
		const { ball, __ } = this.phriend;
		const kept = escape_html(__("Your report is kept."));
		const link = (attr, text) => `<button type="button" class="link" ${attr}>${escape_html(text)}</button>`;
		const again = link("data-retry", __("Try again"));
		const edit = link("data-edit", __("Edit"));
		const text = {
			offline: `${escape_html(__("You're offline."))} ${kept} ${escape_html(__("It goes out when you're back online."))} ${again} · ${edit}`,
			network: `${escape_html(__("The server can't be reached."))} ${kept} ${again} · ${edit}`,
			session: `${escape_html(__("Your session has expired."))} ${kept} ${escape_html(
				__("Log in again in a new tab, then try again.")
			)} <a href="/login" target="_blank" rel="noopener">${escape_html(__("Log in"))}</a> · ${again}`,
			// the page's CSRF token is old (logged in again elsewhere): only a reload gets a new one
			stale: `${escape_html(__("This page is out of date."))} ${escape_html(
				__("Reload it to send your report; the text is kept, the screenshot is not.")
			)} ${link("data-reload", __("Reload"))}`,
			forbidden: `${escape_html(__("You're not allowed to send Phriend reports."))} ${escape_html(error.message || "")} ${link("data-discard-report", __("Discard"))}`,
			server: `${escape_html(__("Sending didn't work:"))} ${escape_html(String(error.message || __("unknown error")).replace(/[.\s]+$/, ""))}. ${kept} ${again} · ${edit}`,
		}[error.kind];
		const bubble = ball.say(text, 0, "point_up");
		const on = (selector, callback) => {
			const el = bubble.querySelector(selector);
			if (el) el.addEventListener("click", callback);
		};
		on("[data-retry]", () => this.retry());
		on("[data-edit]", () => this.edit());
		on("[data-reload]", () => window.location.reload());
		on("[data-discard-report]", () => this.discard());
	}
}
