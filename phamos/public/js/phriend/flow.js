// The report flow: four steps, each one optional.
//   1 Type and priority: what kind of report, how urgent (first, so the user decides what
//     this is before anything else; PM decision 2026-11-15, #1900)
//   2 Screenshot: draw on it, black things out, or leave it out
//   3 What happened: title and description
//   4 Check and send
// Loaded on demand (Desk: phriend_flow.bundle.js, cockpits: a dynamic import), so pages
// don't carry html2canvas until someone wants to report something.

import { Annotator } from "./annotator";
import { SVG } from "./ball";
import { capture, to_data_url } from "./capture";
import { FLOW_CSS } from "./flow_css";
import { call } from "./request";
import { Sender } from "./send";
import { format, from_event } from "./shortcut";
import { DRAFT_KEY, escape_html, sleep, storage_set } from "./util";

// The steps, in their order. The screenshot is taken at the click whatever comes first.
const STEP = { kind: 0, shot: 1, text: 2, check: 3 };
const LAST_STEP = STEP.check;

// picture / crossed-out picture for the "Leave out" / "Use the screenshot" button
const ICON_SHOT = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 16 L9 11 L13 14 L16 12 L21 16"/></svg>';
const ICON_NO_SHOT = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M4 4 L20 20"/></svg>';

// [value stored on the Issue, label, hint]
const TYPES = [
	["Bug", "Bug", "Something is broken"],
	["Idea", "Idea", "It could be better"],
	["Question", "Question", "I'm not sure how"],
	["Other", "Something else", "None of these"],
];
const PRIORITIES = ["Low", "Medium", "High", "Urgent"];
// the ball again, small, for the header; its own gradient id, because the big ball (hidden
// while the flow is open) can't lend its gradient to another drawing
const MINI_SVG = SVG.replace("<svg ", '<svg class="mini" ').replace(/phriend-grad/g, "phriend-grad-mini");

export function open_report(options) {
	return new Flow(options);
}

class Flow {
	constructor({ phriend, ctx, draft, on_close }) {
		this.phriend = phriend;
		this.__ = phriend.__;
		this.ctx = ctx;
		this.on_close = on_close;
		this.step = 0;
		const { canvas, from_failed, has_screenshot, ...text } = draft || {};
		this.values = { title: "", comment: "", report_type: "Bug", priority: "Medium", ...text };
		this.include_screenshot = has_screenshot !== false;
		this.touched = new Set(); // steps the user changed something in
		if (draft && (draft.title || draft.comment)) this.touched.add(STEP.text);
		this.sender = phriend.sender || (phriend.sender = new Sender(phriend));
		// reopened after a failure: the report is back in the flow (and its text in the draft)
		if (from_failed) this.sender.failed = null;

		this.add_styles();
		this.render();
		phriend.ball.set_away(true);
		// above everything the page may open meanwhile (Desk's message boxes sit above 1050)
		phriend.ball.host.style.zIndex = "2147483000";
		this.previous_focus = document.activeElement;
		this.show(draft && (draft.title || draft.comment) ? STEP.text : STEP.kind);
		if (canvas) this.use_screenshot(canvas);
		else this.start_capture();
	}

	add_styles() {
		const shadow = this.phriend.ball.shadow;
		if (shadow.querySelector("style[data-flow]")) return;
		const style = document.createElement("style");
		style.setAttribute("data-flow", "");
		style.textContent = FLOW_CSS;
		shadow.appendChild(style);
	}

	// ------------------------------------------------------------------ DOM

	render() {
		const __ = this.__;
		const where = this.ctx.where || this.ctx.page_title || "";
		const types = TYPES.map(
			([value, label, hint]) =>
				`<button type="button" class="chip" data-type="${value}"><span>${escape_html(__(label))}</span><small>${escape_html(__(hint))}</small></button>`
		).join("");
		const priorities = PRIORITIES.map(
			(value) => `<button type="button" class="chip slim" data-priority="${value}">${escape_html(__(value))}</button>`
		).join("");

		this.layer = document.createElement("div");
		this.layer.className = "overlay";
		this.layer.innerHTML = `
			<div class="panel" role="dialog" aria-modal="true" aria-labelledby="ph-title">
				<header>
					${MINI_SVG}
					<div class="heading">
						<h2 id="ph-title"></h2>
						<p>${escape_html(__("Reported on: {0}", [where]))}</p>
					</div>
					<div class="dots">${[0, 1, 2, 3]
						.map((i) => `<button type="button" class="dot" data-dot="${i}" aria-label="${escape_html(__("Step {0} of 4", [i + 1]))}"></button>`)
						.join("")}</div>
					<button type="button" class="icon-btn" data-close aria-label="${escape_html(__("Close"))}" title="${escape_html(__("Close"))}">
						<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6 L18 18 M18 6 L6 18"/></svg>
					</button>
				</header>
				<main>
					<section class="pane" data-pane="0">
						<label class="field">${escape_html(__("What is it?"))}</label>
						<div class="chips" role="radiogroup">${types}</div>
						<div class="gap"></div>
						<label class="field">${escape_html(__("How urgent is it?"))}</label>
						<div class="chips" role="radiogroup">${priorities}</div>
					</section>
					<section class="pane" data-pane="1" hidden>
						<div class="shot"><div class="skeleton"><span class="spinner"></span>${escape_html(__("Taking a screenshot of the page…"))}</div></div>
						<div class="shot-bar">
							<span class="grow" data-shot-hint>${escape_html(__("Draw an arrow to the problem, box it, write on it, or black out private data."))}</span>
							<button type="button" class="btn with-icon" data-toggle-shot hidden></button>
						</div>
					</section>
					<section class="pane" data-pane="2" hidden>
						<label class="field" for="ph-in-title">${escape_html(__("In a few words"))}</label>
						<input class="input" id="ph-in-title" maxlength="120" autocomplete="off" placeholder="${escape_html(__("Save does nothing on a new lead"))}">
						<div class="gap"></div>
						<label class="field" for="ph-in-comment">${escape_html(__("What did you do, and what did you expect?"))}</label>
						<textarea class="input" id="ph-in-comment" rows="6" placeholder="${escape_html(__("I filled in the company name and clicked Save. Nothing happened."))}"></textarea>
					</section>
					<section class="pane" data-pane="3" hidden></section>
				</main>
				<footer>
					<button type="button" class="link shortcut-link" data-shortcut hidden></button>
					<button type="button" class="btn" data-back>${escape_html(__("Back"))}</button>
					<span class="grow"></span>
					<span class="hint" data-hint>${escape_html(__("Ctrl+Enter sends"))}</span>
					<button type="button" class="btn" data-skip hidden>${escape_html(__("Skip"))}</button>
					<button type="button" class="btn primary" data-next></button>
				</footer>
			</div>`;
		this.phriend.ball.layer.appendChild(this.layer);

		const $ = (selector) => this.layer.querySelector(selector);
		this.el = {
			panel: $(".panel"),
			title: $("#ph-title"),
			shot: $(".shot"),
			shot_hint: $("[data-shot-hint]"),
			toggle_shot: $("[data-toggle-shot]"),
			in_title: $("#ph-in-title"),
			in_comment: $("#ph-in-comment"),
			summary: $('[data-pane="3"]'),
			footer: $("footer"),
			back: $("[data-back]"),
			hint: $("[data-hint]"),
			next: $("[data-next]"),
			skip: $("[data-skip]"),
			shortcut: $("[data-shortcut]"),
		};
		this.el.in_title.value = this.values.title;
		this.el.in_comment.value = this.values.comment;
		this.footer_html = this.el.footer.innerHTML;
		this.bind();
		this.sync_choices();
	}

	bind() {
		const layer = this.layer;
		// a click next to the panel closes it, but not the end of a drag that started on the screenshot
		let down_on_layer = false;
		layer.addEventListener("pointerdown", (e) => (down_on_layer = e.target === layer));
		layer.addEventListener("click", (e) => {
			const t = e.target.closest("button");
			if (!t) {
				if (e.target === layer && down_on_layer) this.close();
				return;
			}
			if (t.hasAttribute("data-close")) this.close();
			else if (t.hasAttribute("data-dot")) this.show(Number(t.dataset.dot));
			else if (t.hasAttribute("data-back")) this.show(this.step - 1);
			else if (t.hasAttribute("data-next")) this.step === LAST_STEP ? this.send() : this.show(this.step + 1);
			else if (t.hasAttribute("data-skip")) this.skip_screenshot();
			else if (t.hasAttribute("data-toggle-shot")) this.toggle_screenshot();
			else if (t.dataset.type) this.choose("report_type", t.dataset.type, STEP.kind);
			else if (t.dataset.priority) this.choose("priority", t.dataset.priority, STEP.kind);
			else if (t.hasAttribute("data-discard")) this.close(true);
			else if (t.hasAttribute("data-keep")) this.restore_footer();
			else if (t.hasAttribute("data-shortcut")) this.edit_shortcut();
			else if (t.hasAttribute("data-sc-off")) this.save_shortcut("Off");
			else if (t.hasAttribute("data-sc-default")) this.save_shortcut("");
			else if (t.hasAttribute("data-sc-cancel")) this.stop_editing_shortcut();
		});
		const typing = (key, step) => (e) => {
			this.values[key] = e.target.value;
			this.touched.add(step);
			this.update_footer();
		};
		this.el.in_title.addEventListener("input", typing("title", STEP.text));
		this.el.in_comment.addEventListener("input", typing("comment", STEP.text));
		this.el.in_title.addEventListener("keydown", (e) => {
			if (e.key === "Enter" && !e.ctrlKey && !e.metaKey && !e.isComposing) {
				e.preventDefault();
				this.el.in_comment.focus();
			}
		});
		// Keys typed inside Phriend reach its fields first, then stop at the host element, so the
		// page's own shortcuts (Desk's Ctrl+S, …) never see them. Keys with the focus elsewhere
		// on the page are caught before the page gets them.
		const host = this.phriend.ball.host;
		this.on_host_key = (e) => {
			this.keydown(e);
			e.stopPropagation();
		};
		this.on_page_key = (e) => {
			if (e.composedPath().includes(host)) return;
			this.keydown(e);
			if (e.key !== "Tab") e.stopPropagation();
		};
		host.addEventListener("keydown", this.on_host_key);
		document.addEventListener("keydown", this.on_page_key, true);
		// the canvas tracks the pointer: count a drawing as a change on the screenshot step
		this.el.shot.addEventListener("pointerup", () => {
			if (this.annotator && this.annotator.has_drawing()) {
				this.touched.add(STEP.shot);
				this.update_footer();
			}
		});
	}

	keydown(e) {
		if (!this.layer.isConnected) return;
		if (this.phriend.recording) return this.record_shortcut(e);
		if (e.key === "Escape") {
			e.preventDefault();
			e.stopPropagation();
			this.close();
		} else if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
			e.preventDefault();
			e.stopPropagation();
			// what the main button does: on to the next step, send on the summary; nothing while
			// "Discard this report?" is asked
			if (this.el.back.isConnected) this.step === LAST_STEP ? this.send() : this.show(this.step + 1);
		} else if (e.key === "Tab") {
			this.trap_focus(e);
		}
	}

	trap_focus(e) {
		const focusable = [...this.layer.querySelectorAll("button, input, textarea, summary, a[href]")].filter(
			(el) => !el.hidden && !el.closest("[hidden]") && el.offsetParent !== null
		);
		if (!focusable.length) return;
		const active = this.phriend.ball.shadow.activeElement;
		const first = focusable[0];
		const last = focusable[focusable.length - 1];
		if (e.shiftKey && (active === first || !this.layer.contains(active))) {
			e.preventDefault();
			last.focus();
		} else if (!e.shiftKey && (active === last || !this.layer.contains(active))) {
			e.preventDefault();
			first.focus();
		}
	}

	// ---------------------------------------------------------------- steps

	show(step) {
		const __ = this.__;
		step = Math.max(0, Math.min(LAST_STEP, step));
		this.step = step;
		this.layer.querySelectorAll(".pane").forEach((pane) => (pane.hidden = Number(pane.dataset.pane) !== step));
		this.layer.querySelectorAll(".dot").forEach((dot, i) => {
			dot.classList.toggle("on", i <= step);
			dot.setAttribute("aria-current", i === step ? "step" : "false");
		});
		this.el.title.textContent = {
			[STEP.kind]: __("What kind of report?"),
			[STEP.shot]: __("Show what you mean"),
			[STEP.text]: __("What happened?"),
			[STEP.check]: __("Check and send"),
		}[step];
		this.el.panel.classList.toggle("narrow", step === STEP.kind || step === STEP.text);
		if (step === STEP.check) this.render_summary();
		this.update_footer();

		const focus = {
			[STEP.kind]: this.layer.querySelector(".chip.on"),
			[STEP.text]: this.el.in_title,
		}[step];
		setTimeout(() => (focus || this.el.next).focus({ preventScroll: true }), 0);
	}

	update_footer() {
		if (!this.el.back.isConnected) return; // the discard question is showing
		const __ = this.__;
		this.el.back.hidden = this.step === 0;
		// Sending happens on the summary only (PM, 2026-11-15): every report passes "Check and
		// send", so nobody sends something they haven't seen.
		this.el.hint.hidden = this.step !== LAST_STEP;
		// the user's own shortcut, changeable here (PM, 2026-11-15); on the first step, where the
		// footer has room and everyone passes
		this.el.shortcut.hidden = this.step !== STEP.kind;
		const keys = format(this.phriend.shortcut);
		this.el.shortcut.textContent = keys ? __("Shortcut: {0}", [keys]) : __("Shortcut: off");
		// The screenshot step: "Next" keeps the screenshot, "Skip" goes on without it (PM,
		// 2026-11-15). Only while there is a screenshot to leave out.
		const on_shot = this.step === STEP.shot;
		this.el.skip.hidden = !(on_shot && this.include_screenshot && !this.capture_failed);
		// an untouched step says "Skip": every step is optional. The type step always has a
		// choice (Bug, Medium), so it says "Next".
		this.el.next.textContent =
			this.step === LAST_STEP
				? __("Send to Phriend")
				: this.touched.has(this.step) || this.step === STEP.kind || on_shot
				? __("Next")
				: __("Skip");
	}

	choose(key, value, step) {
		this.values[key] = value;
		this.touched.add(step);
		this.sync_choices();
		this.update_footer();
	}

	sync_choices() {
		this.layer.querySelectorAll("[data-type]").forEach((b) => {
			const on = b.dataset.type === this.values.report_type;
			b.classList.toggle("on", on);
			b.setAttribute("role", "radio");
			b.setAttribute("aria-checked", on ? "true" : "false");
		});
		this.layer.querySelectorAll("[data-priority]").forEach((b) => {
			const on = b.dataset.priority === this.values.priority;
			b.classList.toggle("on", on);
			b.setAttribute("role", "radio");
			b.setAttribute("aria-checked", on ? "true" : "false");
		});
	}

	// the title the server uses when it's left empty (shown greyed out): where it happened
	built_title() {
		return this.ctx.where || this.ctx.page_title || this.ctx.route || "";
	}

	render_summary() {
		const __ = this.__;
		const v = this.values;
		const ctx = this.ctx;
		const c = ctx.context || {};
		const shot = this.screenshot_canvas();
		const errors = (c.recent_errors || []).length;
		const failed = (c.failed_requests || []).length;
		const facts = [
			[__("Page"), ctx.where || ctx.page_title || ctx.route],
			[__("Address"), ctx.page_url],
			[__("Browser"), browser_name(c.user_agent)],
			[__("Window"), c.viewport],
			[__("Version"), version_of(c.versions)],
			[__("Problems on the page"), errors || failed ? __("{0} errors, {1} failed calls", [errors, failed]) : __("None")],
		].filter(([, value]) => value);

		this.el.summary.innerHTML = `
			<div class="summary">
				<div>
					<h3 class="${v.title.trim() ? "" : "built"}">${escape_html(v.title.trim() || this.built_title())}</h3>
					<p class="meta">${escape_html(
						[__(type_label(v.report_type)), __(v.priority), shot ? __("with screenshot") : __("no screenshot")].join(" · ")
					)}</p>
					${v.comment.trim() ? `<p class="comment">${escape_html(v.comment.trim())}</p>` : ""}
					<p class="facts-title">${escape_html(__("Phriend adds this for you"))}</p>
					${facts.map(([k, val]) => `<div class="fact"><span>${escape_html(k)}</span><span>${escape_html(val)}</span></div>`).join("")}
					<details><summary>${escape_html(__("Everything that is sent"))}</summary><pre></pre></details>
				</div>
				<div>${shot ? `<img class="thumb" alt="${escape_html(__("Screenshot"))}">` : ""}</div>
			</div>`;
		this.el.summary.querySelector("pre").textContent = JSON.stringify(this.args_without_screenshot(), null, 2);
		if (shot) this.el.summary.querySelector("img").src = shot.toDataURL("image/jpeg", 0.7);
	}

	// ----------------------------------------------------------- screenshot

	// The promise is set at once, so send() always waits for it. The capture only starts while
	// the flow is still open: it may change the page for a moment (capture.js), and the flow
	// covers the page while it does.
	start_capture() {
		const key = this.ctx.ref_doctype || String(this.ctx.route || "").split("/")[0] || "page";
		this.capturing = (async () => {
			await sleep(180); // let the panel appear first: drawing the page holds up the browser
			if (!this.layer.isConnected) throw new Error("closed before the screenshot");
			return capture(key);
		})();
		this.capturing.then(
			({ canvas }) => this.layer.isConnected && this.use_screenshot(canvas),
			(e) => {
				console.warn("Phriend could not take a screenshot", e);
				this.capture_failed = true;
				if (this.layer.isConnected) this.show_no_screenshot();
			}
		);
	}

	use_screenshot(canvas) {
		this.annotator = new Annotator(this.el.shot, canvas, this.__);
		this.el.toggle_shot.hidden = false;
		this.sync_screenshot_state(); // also right when "Skip" was pressed before it was ready
		this.update_footer();
	}

	show_no_screenshot() {
		const __ = this.__;
		this.el.shot.innerHTML = `<div class="no-shot"><strong>${escape_html(
			__("No screenshot this time.")
		)}</strong><span>${escape_html(__("Describe what you see in the next step instead."))}</span></div>`;
		this.el.shot_hint.textContent = "";
		this.update_footer(); // nothing to skip any more
	}

	toggle_screenshot() {
		this.include_screenshot = !this.include_screenshot;
		this.touched.add(STEP.shot);
		this.sync_screenshot_state();
		this.update_footer();
	}

	// "Skip" on the screenshot step: on to the next step, without the screenshot. Coming back,
	// "Use the screenshot" brings it back.
	skip_screenshot() {
		if (this.include_screenshot) this.toggle_screenshot();
		this.show(STEP.shot + 1);
	}

	sync_screenshot_state() {
		const __ = this.__;
		const on = this.include_screenshot;
		const wrap = this.el.shot.querySelector(".annotator");
		if (wrap) wrap.style.opacity = on ? "" : "0.25";
		this.el.toggle_shot.innerHTML = `${on ? ICON_NO_SHOT : ICON_SHOT}<span>${escape_html(
			on ? __("Leave out the screenshot") : __("Use the screenshot")
		)}</span>`;
		this.el.toggle_shot.setAttribute("aria-pressed", on ? "false" : "true");
		this.el.shot_hint.textContent = on
			? __("Draw an arrow to the problem, box it, write on it, or black out private data.")
			: __("The report goes out without a screenshot.");
	}

	screenshot_canvas() {
		if (!this.include_screenshot || !this.annotator) return null;
		return this.annotator.result();
	}

	// ----------------------------------------------------------------- send

	args_without_screenshot() {
		const v = this.values;
		const ctx = this.ctx;
		return {
			title: v.title.trim(),
			comment: v.comment.trim(),
			report_type: v.report_type,
			priority: v.priority,
			route: ctx.route || "",
			page_url: ctx.page_url,
			page_title: ctx.where || ctx.page_title || "",
			ref_doctype: ctx.ref_doctype || null,
			ref_docname: ctx.ref_docname || null,
			context: ctx.context,
		};
	}

	send() {
		const args = this.args_without_screenshot();
		const include = this.include_screenshot && !this.capture_failed;
		const capturing = this.capturing;
		const flow = this;
		const report = {
			draft: {
				title: this.values.title,
				comment: this.values.comment,
				report_type: this.values.report_type,
				priority: this.values.priority,
				has_screenshot: include,
			},
			canvas: null, // the screenshot with the drawing, kept for "Edit" after a failure
			// waits for a screenshot still being taken, then encodes it: after the flow closed
			async args() {
				let canvas = null;
				if (include && flow.annotator) {
					canvas = flow.annotator.result();
				} else if (include && capturing) {
					try {
						canvas = (await capturing).canvas;
					} catch (e) {
						canvas = null; // send without it
					}
				}
				report.canvas = canvas;
				flow.annotator = null;
				return { ...args, context: JSON.stringify(args.context), screenshot: canvas ? to_data_url(canvas) : null };
			},
		};
		this.close(true, true);
		this.sender.send(report);
	}

	// ---------------------------------------------------------------- close

	is_dirty() {
		return this.values.title.trim() || this.values.comment.trim() || (this.annotator && this.annotator.has_drawing());
	}

	close(force = false, sent = false) {
		if (this.phriend.recording) return this.stop_editing_shortcut();
		if (!force && this.is_dirty()) return this.ask_discard();
		const ball = this.phriend.ball;
		ball.host.removeEventListener("keydown", this.on_host_key);
		document.removeEventListener("keydown", this.on_page_key, true);
		if (!sent) this.annotator = null;
		if (!sent && !this.sender.busy()) {
			// closed without sending: a draft kept from an earlier failure goes too (the user
			// confirmed that when there was text; with none there is nothing to lose)
			storage_set(DRAFT_KEY, null, "session");
			ball.set_pending(false);
		}
		this.phriend.recording = false;
		const finish = () => {
			this.layer.remove();
			ball.set_away(false);
			ball.host.style.zIndex = "";
			this.on_close();
		};
		// Sent while the screenshot is still being taken: the panel goes at once, the dimmed
		// page stays until the capture is done (it may shift the page for a moment).
		if (sent && this.capturing && !this.annotator && !this.capture_failed) {
			this.el.panel.remove();
			this.capturing.then(finish, finish);
		} else {
			finish();
		}
		if (this.previous_focus && this.previous_focus.focus) {
			try {
				this.previous_focus.focus({ preventScroll: true });
			} catch (e) {
				// the element is gone
			}
		}
	}

	// ------------------------------------------------------------- shortcut

	edit_shortcut() {
		const __ = this.__;
		const fallback = format(this.phriend.host.default_shortcut);
		this.phriend.recording = true;
		this.el.footer.innerHTML = `
			<span class="confirm grow" data-sc-msg aria-live="polite">${escape_html(__("Press the new keys…"))}</span>
			<button type="button" class="btn" data-sc-off>${escape_html(__("Turn off"))}</button>
			${fallback ? `<button type="button" class="btn" data-sc-default>${escape_html(__("Use the default ({0})", [fallback]))}</button>` : ""}
			<button type="button" class="btn ghost" data-sc-cancel>${escape_html(__("Cancel"))}</button>`;
		setTimeout(() => this.el.footer.querySelector("[data-sc-cancel]").focus(), 0);
	}

	record_shortcut(e) {
		e.preventDefault();
		e.stopPropagation();
		if (e.key === "Escape") return this.stop_editing_shortcut();
		if (["Shift", "Control", "Alt", "Meta", "Tab"].includes(e.key)) return; // still choosing
		const text = from_event(e);
		if (text) return this.save_shortcut(text);
		this.shortcut_message(this.__("Use Cmd/Ctrl or Alt together with a letter, a digit or F1 to F12."));
	}

	async save_shortcut(value) {
		const __ = this.__;
		this.shortcut_message(__("Saving…"));
		try {
			const now = await call("phamos.phriend.api.set_my_shortcut", { shortcut: value }, this.phriend.host.csrf_token());
			this.phriend.set_shortcut(now || "");
			this.stop_editing_shortcut();
		} catch (error) {
			this.shortcut_message(error.message || __("That didn't work. Try again."));
		}
	}

	shortcut_message(text) {
		const el = this.el.footer.querySelector("[data-sc-msg]");
		if (el) el.textContent = text;
	}

	stop_editing_shortcut() {
		this.phriend.recording = false;
		this.restore_footer();
	}

	ask_discard() {
		const __ = this.__;
		this.el.footer.innerHTML = `
			<span class="confirm grow">${escape_html(__("Discard this report? What you wrote and drew is lost."))}</span>
			<button type="button" class="btn" data-keep>${escape_html(__("Keep editing"))}</button>
			<button type="button" class="btn danger" data-discard>${escape_html(__("Discard"))}</button>`;
		setTimeout(() => this.el.footer.querySelector("[data-keep]").focus(), 0);
	}

	restore_footer() {
		this.el.footer.innerHTML = this.footer_html;
		this.el.back = this.layer.querySelector("[data-back]");
		this.el.hint = this.layer.querySelector("[data-hint]");
		this.el.next = this.layer.querySelector("[data-next]");
		this.el.skip = this.layer.querySelector("[data-skip]");
		this.el.shortcut = this.layer.querySelector("[data-shortcut]");
		this.update_footer();
		this.el.next.focus();
	}
}

function type_label(value) {
	const type = TYPES.find(([v]) => v === value);
	return type ? type[1] : value;
}

function version_of(versions) {
	if (!versions) return "";
	if (versions.phamos) return `phamos ${versions.phamos}`;
	return versions.frappe ? `Frappe ${versions.frappe}` : "";
}

function browser_name(ua) {
	if (!ua) return "";
	const match =
		ua.match(/(Edg|OPR|Firefox|Chrome|Version)\/(\d+)/) || ua.match(/(Safari)\/(\d+)/) || [];
	const names = { Edg: "Edge", OPR: "Opera", Version: "Safari" };
	return match[1] ? `${names[match[1]] || match[1]} ${match[2]}` : "";
}

// for checking a capture from the browser console: (await phriend_flow.capture("page")).canvas
export { capture } from "./capture";
