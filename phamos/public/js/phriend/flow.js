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
import { IS_MAC, format, from_event, problem } from "./shortcut";
import { DRAFT_KEY, browser_name, escape_html, sleep, storage_set } from "./util";

// The steps, in their order. The screenshot is taken at the click whatever comes first.
const STEP = { kind: 0, shot: 1, text: 2, check: 3 };
const LAST_STEP = STEP.check;

// picture / crossed-out picture for the "Leave out" / "Use the screenshot" button
const ICON_SHOT = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 16 L9 11 L13 14 L16 12 L21 16"/></svg>';
const ICON_NO_SHOT = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M4 4 L20 20"/></svg>';

// [value stored on the Issue, label, hint]
const TYPES = [
	["Bug", "Bug", "Something is broken"],
	["Improvement", "Improvement", "It could be better"], // not "Idea": that reads as a cockpit Idea (#1924)
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
		this.load_reported();
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
						<p>${escape_html(__("About: {0}", [where]))}</p>
					</div>
					<div class="dots">${[0, 1, 2, 3]
						.map((i) => {
							const name = escape_html(__("Step {0} of 4: {1}", [i + 1, this.step_title(i)]));
							return `<button type="button" class="dot" data-dot="${i}" aria-label="${name}" title="${name}"></button>`;
						})
						.join("")}</div>
					<span class="sr-only" data-announce aria-live="polite"></span>
					<button type="button" class="icon-btn" data-close aria-label="${escape_html(__("Close"))}" title="${escape_html(__("Close"))}">
						<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6 L18 18 M18 6 L6 18"/></svg>
					</button>
				</header>
				<main>
					<section class="pane" data-pane="0">
						<p class="field" id="ph-type-label">${escape_html(__("Type"))}</p>
						<div class="chips" role="radiogroup" aria-labelledby="ph-type-label" data-group="report_type">${types}</div>
						<div class="gap"></div>
						<p class="field" id="ph-priority-label">${escape_html(__("How urgent is it?"))}</p>
						<div class="chips" role="radiogroup" aria-labelledby="ph-priority-label" data-group="priority">${priorities}</div>
						<section class="reported" data-reported aria-live="polite">
							<p class="reported-empty">${escape_html(__("Looking for earlier reports…"))}</p>
						</section>
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
						<input class="input" id="ph-in-title" maxlength="120" autocomplete="off" placeholder="${escape_html(__("e.g. Save does nothing on a new lead"))}">
						<div class="gap"></div>
						<label class="field" for="ph-in-comment">${escape_html(__("What did you do, and what did you expect?"))}</label>
						<textarea class="input" id="ph-in-comment" rows="6" placeholder="${escape_html(__("e.g. I filled in the company name and clicked Save. Nothing happened."))}"></textarea>
					</section>
					<section class="pane" data-pane="3" hidden></section>
				</main>
				<footer>
					<button type="button" class="link shortcut-link" data-shortcut hidden></button>
					<button type="button" class="btn" data-back>${escape_html(__("Back"))}</button>
					<span class="grow"></span>
					<span class="hint" data-hint></span>
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
			announce: $("[data-announce]"),
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
		const asking = !this.el.back.isConnected; // "Discard this report?" is showing
		if (e.key === "Escape") {
			e.preventDefault();
			e.stopPropagation();
			if (asking) this.restore_footer(); // Escape means "Keep editing" there
			else this.close();
		} else if (!asking && this.step === STEP.shot && this.shot_key(e)) {
			e.preventDefault();
		} else if (!asking && this.step === STEP.kind && this.chip_key(e)) {
			e.preventDefault();
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

	// On the screenshot step: Cmd/Ctrl+Z undoes, a letter picks a tool (shown in the tooltips).
	// Not while typing on the screenshot. True when the key was used.
	shot_key(e) {
		const a = this.annotator;
		if (!a || !this.include_screenshot || a.editing) return false;
		const mod = IS_MAC ? e.metaKey : e.ctrlKey;
		if (mod && !e.altKey && !e.shiftKey && String(e.key).toLowerCase() === "z") {
			a.undo();
			return true;
		}
		if (e.ctrlKey || e.metaKey || e.altKey) return false;
		return a.select_tool_by_key(String(e.key).toLowerCase());
	}

	// Type and urgency behave as radio groups: arrow keys move the choice, Enter goes on.
	chip_key(e) {
		const chip = this.phriend.ball.shadow.activeElement;
		const group = chip && chip.closest && chip.closest("[data-group]");
		if (!group || e.ctrlKey || e.metaKey || e.altKey) return false;
		if (e.key === "Enter") {
			chip.click();
			this.show(this.step + 1);
			return true;
		}
		const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
		if (!step) return false;
		const chips = [...group.querySelectorAll(".chip")];
		const next = chips[(chips.indexOf(chip) + step + chips.length) % chips.length];
		next.click();
		next.focus();
		return true;
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
		this.el.title.textContent = this.step_title(step);
		// for screen readers, which don't notice the heading change
		this.el.announce.textContent = __("Step {0} of 4: {1}", [step + 1, this.step_title(step)]);
		if (step === STEP.shot && this.annotator) this.shot_seen = true;
		if (step === STEP.check) this.render_summary();
		this.update_footer();

		const focus = {
			[STEP.kind]: this.layer.querySelector(".chip.on"),
			[STEP.text]: this.el.in_title,
		}[step];
		setTimeout(() => (focus || this.el.next).focus({ preventScroll: true }), 0);
	}

	step_title(step) {
		const __ = this.__;
		return {
			[STEP.kind]: __("What kind of report?"),
			[STEP.shot]: __("Show what you mean"),
			[STEP.text]: __("What happened?"),
			[STEP.check]: __("Check and send"),
		}[step];
	}

	update_footer() {
		if (!this.el.back.isConnected) return; // the discard question is showing
		const __ = this.__;
		this.el.back.hidden = this.step === 0;
		// Sending happens on the summary only (PM, 2026-11-15): every report passes "Check and
		// send", so nobody sends something they haven't seen.
		// Cmd/Ctrl+Enter does what the main button does, on every step
		const enter = IS_MAC ? "⌘↩" : "Ctrl+Enter";
		this.el.hint.textContent = this.step === LAST_STEP ? __("{0} sends", [enter]) : __("{0} next", [enter]);
		// the user's own shortcut, changeable here (PM, 2026-11-15); on the first step, where the
		// footer has room and everyone passes
		this.el.shortcut.hidden = this.step !== STEP.kind;
		const keys = format(this.phriend.shortcut);
		this.el.shortcut.textContent = keys ? __("Shortcut: {0} · Change", [keys]) : __("Shortcut: off · Change");
		// The screenshot step: "Next" keeps the screenshot, "Skip" goes on without it (PM,
		// 2026-11-15). Only while there is a screenshot to leave out.
		const on_shot = this.step === STEP.shot;
		this.el.skip.hidden = !(on_shot && this.include_screenshot && !this.capture_failed);
		// always "Next": every step is optional anyway, and a label that changes while typing
		// moves the button (UX review of !1162)
		this.el.next.textContent = this.step === LAST_STEP ? __("Send to Phriend") : __("Next");
	}

	choose(key, value, step) {
		this.values[key] = value;
		this.touched.add(step);
		this.sync_choices();
		this.update_footer();
	}

	sync_choices() {
		// one Tab stop per group (the chosen chip); arrow keys move within it (chip_key)
		const mark = (selector, key, value) =>
			this.layer.querySelectorAll(selector).forEach((b) => {
				const on = b.dataset[key] === value;
				b.classList.toggle("on", on);
				b.setAttribute("role", "radio");
				b.setAttribute("aria-checked", on ? "true" : "false");
				b.tabIndex = on ? 0 : -1;
			});
		mark("[data-type]", "type", this.values.report_type);
		mark("[data-priority]", "priority", this.values.priority);
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
		const waiting = this.include_screenshot && !this.annotator && !this.capture_failed;
		if (shot) this.shot_seen = true; // the thumbnail below shows it
		const errors = (c.recent_errors || []).length;
		const failed = (c.failed_requests || []).length;
		const problems = [
			errors ? (errors === 1 ? __("1 error") : __("{0} errors", [errors])) : "",
			failed ? (failed === 1 ? __("1 failed call") : __("{0} failed calls", [failed])) : "",
		].filter(Boolean).join(", ");
		const facts = [
			[__("Page"), ctx.where || ctx.page_title || ctx.route],
			[__("Address"), ctx.page_url],
			[__("Browser"), c.browser],
			[__("Window"), c.viewport],
			[__("Version"), version_of(c.versions)],
			[__("Problems on the page"), problems || __("None")],
		].filter(([, value]) => value);

		this.el.summary.innerHTML = `
			<div class="summary">
				<div>
					<button type="button" class="to-step" data-dot="${STEP.text}" title="${escape_html(__("Change"))}">
						<h3 class="${v.title.trim() ? "" : "built"}">${escape_html(v.title.trim() || this.built_title())}</h3>
					</button>
					<button type="button" class="to-step" data-dot="${STEP.kind}" title="${escape_html(__("Change"))}">
						<p class="meta">${escape_html(
							[
								__(type_label(v.report_type)),
								__(v.priority),
								shot ? __("with screenshot") : waiting ? __("screenshot still being taken…") : __("no screenshot"),
							].join(" · ")
						)}</p>
					</button>
					${v.comment.trim() ? `<button type="button" class="to-step" data-dot="${STEP.text}" title="${escape_html(__("Change"))}"><p class="comment">${escape_html(v.comment.trim())}</p></button>` : ""}
					<p class="facts-title">${escape_html(__("Phriend adds this for you"))}</p>
					${facts.map(([k, val]) => `<div class="fact"><span>${escape_html(k)}</span><span>${escape_html(val)}</span></div>`).join("")}
					<details><summary>${escape_html(__("Everything that is sent"))}</summary><pre></pre></details>
				</div>
				<div>${shot ? `<button type="button" class="to-step" data-dot="${STEP.shot}" title="${escape_html(__("Change"))}"><img class="thumb" alt="${escape_html(__("Screenshot"))}"></button>` : ""}</div>
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
		if (this.step === STEP.shot) this.shot_seen = true;
		if (this.step === STEP.check) this.render_summary(); // it said "still being taken"
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
		// left out: dimmed, and nothing to draw on
		if (wrap) wrap.classList.toggle("off", !on);
		this.el.toggle_shot.innerHTML = `${on ? ICON_NO_SHOT : ICON_SHOT}<span>${escape_html(
			on ? __("Leave out the screenshot") : __("Use the screenshot")
		)}</span>`;
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
		// Only a screenshot the user has seen goes out: on the screenshot step or as the thumbnail
		// on the summary. One still being taken, or not looked at, stays here (GDPR review of
		// !1162: an unseen screenshot can't have been blacked out).
		const include = this.include_screenshot && !this.capture_failed && Boolean(this.annotator) && this.shot_seen;
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
			// encodes the screenshot after the flow closed, so closing feels instant
			async args() {
				const canvas = include && flow.annotator ? flow.annotator.result() : null;
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

	// ------------------------------------------------------------- reported

	// The open reports about this page or record, on the first step: someone may have reported
	// it already (PM, 2026-11-15). Each opens in a new tab, so the report in progress stays.
	async load_reported() {
		const __ = this.__;
		const box = this.layer.querySelector("[data-reported]");
		let result;
		try {
			result = await call(
				"phamos.phriend.api.get_open_reports",
				{ route: this.ctx.route || "", ref_doctype: this.ctx.ref_doctype || "", ref_docname: this.ctx.ref_docname || "" },
				this.phriend.host.csrf_token()
			);
		} catch (e) {
			box.hidden = true; // not worth a message: reporting still works
			return;
		}
		if (!box.isConnected) return;
		const reports = (result && result.reports) || [];
		// Where the reports about this place stand, in the Implementation Cockpit (#1671)
		const cockpit = this.phriend.host.open_status
			? `<button type="button" class="link reported-cockpit" data-reported-cockpit>${escape_html(__("See their status"))} ↗</button>`
			: "";
		const bind_cockpit = () => {
			const link = box.querySelector("[data-reported-cockpit]");
			if (link) link.addEventListener("click", () => this.phriend.host.open_status(this.ctx));
		};
		if (!reports.length) {
			box.innerHTML = `<p class="reported-empty">${escape_html(__("No open reports about this page yet."))}${cockpit}</p>`;
			bind_cockpit();
			return;
		}
		// one row per report, in columns that line up across rows: type, title, reporter, age, status
		const items = reports
			.map(
				(r) => `<li><a href="${escape_html(this.phriend.host.issue_url(r.name))}" target="_blank" rel="noopener">
					<span class="reported-type"><span>${escape_html(__(type_label(r.type)))}</span></span>
					<span class="reported-title" title="${escape_html(r.title)}">${escape_html(r.title)}</span>
					<span class="reported-by" title="${escape_html(r.reported_by)}">${escape_html(r.reported_by)}</span>
					<span class="reported-when">${escape_html(r.when)}</span>
					<span class="reported-status">${escape_html(r.status)}</span>
				</a></li>`
			)
			.join("");
		const more =
			result.count > reports.length && this.phriend.host.open_reports
				? `<button type="button" class="link reported-all" data-reported-all>${escape_html(__("Show all {0}", [result.count]))}</button>`
				: "";
		box.innerHTML = `
			<p class="reported-head">${escape_html(__("Already reported here"))} <span class="reported-count">${escape_html(String(result.count))}</span>${cockpit}</p>
			<ul>${items}</ul>${more}`;
		const all = box.querySelector("[data-reported-all]");
		if (all) all.addEventListener("click", () => this.phriend.host.open_reports());
		bind_cockpit();
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
		if (e.key === "Escape") {
			e.preventDefault();
			e.stopPropagation();
			return this.stop_editing_shortcut();
		}
		// Tab, Enter and Space reach the buttons ("Turn off", "Use the default", "Cancel"), so
		// the editor works from the keyboard; none of them can be a shortcut anyway
		const plain = !e.ctrlKey && !e.metaKey && !e.altKey;
		if (e.key === "Tab") return this.trap_focus(e);
		if (plain && (e.key === "Enter" || e.key === " ")) return;
		e.preventDefault();
		e.stopPropagation();
		if (this.saving_shortcut || ["Shift", "Control", "Alt", "Meta"].includes(e.key)) return;
		const text = from_event(e);
		if (!text) return;
		const why = problem(text);
		if (why) return this.shortcut_message(this.shortcut_problem(why, text));
		this.save_shortcut(text);
	}

	// The reasons problem() in shortcut.js gives, in words; the server says the same.
	shortcut_problem(why, text) {
		const __ = this.__;
		const keys = format(text) || text;
		return {
			modifier: __("Use Cmd/Ctrl together with a letter, a digit or F1 to F12."),
			alt: __("Alt/Option is not possible: it types characters such as @ or € on many keyboards."),
			reserved: __("{0} belongs to the browser or the system (copy, paste, undo, tabs…).", [keys]),
		}[why];
	}

	async save_shortcut(value) {
		const __ = this.__;
		if (this.saving_shortcut) return; // one save at a time: a second key press waits
		this.saving_shortcut = true;
		this.shortcut_message(__("Saving…"));
		try {
			const now = await call("phamos.phriend.api.set_my_shortcut", { shortcut: value }, this.phriend.host.csrf_token());
			this.phriend.set_shortcut(now || "");
			this.stop_editing_shortcut();
		} catch (error) {
			this.shortcut_message(error.message || __("That didn't work. Try again."));
		} finally {
			this.saving_shortcut = false;
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


// for checking a capture from the browser console: (await phriend_flow.capture("page")).canvas
export { capture } from "./capture";
