// One voice (#2011): everything Phriend says by itself goes through here.
//
//   reaction  an emoji, no words; never counted (Phriend.react)
//   note      waits behind the blue dot until the user clicks it
//   question  opens a bubble if one of today's bubbles is left (Phriend Settings → Bubbles per
//             day, counted on the server), else waits behind the dot (or is dropped)
//   warning   ‼️ at once, also while quiet and while someone types, also over another bubble;
//             it only waits while the report flow or the menu is open (PM, 2026-11-21); behind
//             the dot while warnings are muted
//
// Never while someone types, never over another bubble, the menu or the report flow: then it
// tries again a little later. What the user does themselves (reports, "Report it?" after a
// failed call) doesn't go through here and doesn't count (PM, 2026-11-21).

import { call } from "./request";

const TYPING_MS = 4000; // a key pressed this recently counts as typing
const RETRY_MS = 5000;
const RETRIES = 6; // then behind the dot
const BUBBLE_MS = 8000;
const WARN_WAIT_MS = 1000; // a warning checks this often whether the report flow is closed
const WARN_WAIT_MAX = 30 * 60; // then behind the dot (half an hour of an open report flow)

// The browser's own calendar day: "a day" is the user's day, not the server's.
export function local_day(now) {
	const d = new Date(now);
	const pad = (n) => String(n).padStart(2, "0");
	return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

// state: { day, used, limit } as the server keeps it
export function has_budget(state, day) {
	if (!state) return false;
	const used = state.day === day ? state.used : 0;
	return used < state.limit;
}

export function is_editable(el) {
	if (!el) return false;
	const tag = (el.tagName || "").toLowerCase();
	if (tag === "textarea" || tag === "select") return true;
	if (tag === "input") return !["button", "submit", "checkbox", "radio", "reset", "range", "color", "file"].includes((el.type || "").toLowerCase());
	return !!el.isContentEditable;
}

export function is_typing(active, last_key_at, now) {
	return is_editable(active) || now - (last_key_at || 0) < TYPING_MS;
}

// the focused element, also inside shadow roots (cockpit widgets)
function deep_active() {
	let el = document.activeElement;
	while (el && el.shadowRoot && el.shadowRoot.activeElement) el = el.shadowRoot.activeElement;
	return el;
}

export class Voice {
	constructor(phriend) {
		this.phriend = phriend;
		this.state = phriend.host.voice || null;
		this.waiting = [];
		this.last_key_at = 0;
		document.addEventListener("keydown", () => (this.last_key_at = Date.now()), true);
	}

	enabled() {
		const features = this.phriend.host.features || {};
		return !!features.one_voice;
	}

	busy() {
		const p = this.phriend;
		const ball = p.ball;
		return !ball || p.open || document.hidden || ball.bubble_showing() || ball.menu_open();
	}

	typing() {
		return is_typing(deep_active(), this.last_key_at, Date.now());
	}

	// item: { html (trusted markup), gesture, ms, bind(bubble) }. Resolves true when it showed.
	async ask(item, { drop = false } = {}) {
		if (!this.enabled()) return this.show(item); // as before the voice existed
		for (let attempt = 0; ; attempt++) {
			if (this.phriend.is_quiet()) return this.later(item, drop);
			if (!this.busy() && !this.typing()) break;
			if (attempt >= RETRIES) return this.later(item, drop);
			await new Promise((r) => setTimeout(r, RETRY_MS));
		}
		if (!(await this.claim())) return this.later(item, drop);
		// the bubble is paid for: if something came first while asking, wait for it instead of
		// losing it (AI review of !1276)
		for (let attempt = 0; this.busy(); attempt++) {
			if (attempt >= RETRIES) return this.later(item, false);
			await new Promise((r) => setTimeout(r, RETRY_MS));
		}
		return this.show(item);
	}

	note(item) {
		if (!this.enabled()) return this.show(item);
		this.later(item, false);
		return false;
	}

	async warn(item) {
		const warning = { ...item, gesture: "alert" };
		if (this.phriend.warnings_muted()) return this.later(warning, false);
		// never on top of the report flow or the menu: the moment they close (PM, 2026-11-21)
		for (let waited = 0; this.phriend.open || (this.phriend.ball && this.phriend.ball.menu_open()); waited++) {
			if (waited >= WARN_WAIT_MAX) return this.later(warning, false);
			await new Promise((r) => setTimeout(r, WARN_WAIT_MS));
		}
		return this.show(warning);
	}

	// One of today's bubbles, from the server (it counts across tabs and devices).
	async claim() {
		const day = local_day(Date.now());
		if (!has_budget(this.state, day)) return false;
		try {
			const result = await call(
				"phamos.phriend.api.claim_my_bubble",
				{ day },
				this.phriend.host.csrf_token()
			);
			this.state = result;
			return !!result.granted;
		} catch (e) {
			return false; // can't tell: rather stay quiet
		}
	}

	later(item, drop) {
		if (!drop) {
			this.waiting.push(item);
			this.update_dot();
		}
		return false;
	}

	show(item) {
		const ball = this.phriend.ball;
		if (!ball) return false;
		ball.say(item.html, item.ms ?? BUBBLE_MS, item.gesture || null);
		if (item.bind) item.bind(ball.bubble);
		return true;
	}

	// The dot: the oldest waiting item, in a bubble that stays until closed. Never counted.
	open_next() {
		const item = this.waiting.shift();
		this.update_dot();
		if (item) this.show({ ...item, ms: 0 });
	}

	update_dot() {
		const ball = this.phriend.ball;
		if (ball) ball.set_waiting(this.waiting.length);
	}
}
