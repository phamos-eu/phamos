// Phriend: a little black ball with legs that lives in the desk.
// Click it (or Ctrl+Shift+B) -> screenshot -> annotate + comment -> Issue assigned to you.

import html2canvas from "html2canvas";
import { toCanvas as html_to_canvas } from "html-to-image";

const MAX_LOG = 20;
const POS_KEY = "phriend:position";
const GREETED_KEY = "phriend:greeted";
const DEBUG_KEY = "phriend:debug"; // localStorage.setItem("phriend:debug", 1) for html2canvas logs
const CAPTURE_TIMEOUT_MS = 25000; // whole capture, both engines
const HTML2CANVAS_TIMEOUT_MS = 10000; // then fall back to html-to-image
// remembers per DocType when html2canvas failed and html-to-image is used instead
const ENGINE_KEY_PREFIX = "phriend:engine:v3:";
const KEEP_TAGS = new Set(["HEAD", "LINK", "STYLE", "META", "TITLE", "BASE"]);
const REPORT_DOCTYPE = "Issue"; // where reports are stored
const CLOSED_STATUSES = ["Resolved", "Closed"];

const SVG = `
<svg viewBox="0 0 64 76" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
	<defs>
		<radialGradient id="phriend-grad" cx="35%" cy="30%" r="75%">
			<stop offset="0%" stop-color="#4a4a4a"/>
			<stop offset="45%" stop-color="#151515"/>
			<stop offset="100%" stop-color="#000"/>
		</radialGradient>
	</defs>
	<ellipse class="phriend-shadow" cx="32" cy="72" rx="16" ry="3" fill="#000" opacity="0.25"/>
	<g class="phriend-body">
		<g class="phriend-leg phriend-leg-l">
			<path d="M24 48 L20 66" stroke="#111" stroke-width="4" stroke-linecap="round"/>
			<ellipse cx="17.5" cy="67" rx="5.5" ry="2.6" fill="#111"/>
		</g>
		<g class="phriend-leg phriend-leg-r">
			<path d="M40 48 L44 66" stroke="#111" stroke-width="4" stroke-linecap="round"/>
			<ellipse cx="46.5" cy="67" rx="5.5" ry="2.6" fill="#111"/>
		</g>
		<circle class="phriend-ball" cx="32" cy="32" r="24" fill="url(#phriend-grad)"/>
		<ellipse cx="23" cy="20" rx="6" ry="3.5" fill="#fff" opacity="0.16" transform="rotate(-30 23 20)"/>
		<g class="phriend-eyes">
			<ellipse cx="24" cy="30" rx="5.5" ry="6.5" fill="#fff"/>
			<ellipse cx="40" cy="30" rx="5.5" ry="6.5" fill="#fff"/>
			<circle class="phriend-pupil" cx="24" cy="31" r="2.8" fill="#111"/>
			<circle class="phriend-pupil" cx="40" cy="31" r="2.8" fill="#111"/>
		</g>
		<path d="M27 42 Q32 46.5 37 42" stroke="#fff" stroke-width="1.8" fill="none" stroke-linecap="round" opacity="0.85"/>
	</g>
</svg>`;

class Phriend {
	constructor() {
		this.errors = [];
		this.failed_requests = [];
		this.busy = false;
		this.watch_errors();
	}

	// ---------------------------------------------------------------- setup

	mount() {
		if (document.getElementById("phriend-root")) return;

		this.$root = $(`
			<div id="phriend-root" title="${__("Phriend: click to report an issue (Ctrl+Shift+B)")}">
				<div class="phriend-bubble"></div>
				${SVG}
				<span class="phriend-badge" data-count="0"></span>
			</div>
		`).appendTo(document.body);

		this.root = this.$root.get(0);
		this.$bubble = this.$root.find(".phriend-bubble");
		this.$badge = this.$root.find(".phriend-badge");
		this.pupils = this.root.querySelectorAll(".phriend-pupil");

		this.restore_position();
		this.setup_drag();
		this.setup_eyes();
		this.setup_shortcut();
		this.setup_route_watch();

		this.$badge.on("pointerdown", (e) => e.stopPropagation());
		this.$badge.on("click", (e) => {
			e.stopPropagation();
			this.open_reports_for_page();
		});

		$(window).on("resize", () => this.clamp_into_view());

		if (!this.storage_get(GREETED_KEY)) {
			this.say(__("Hi, I'm Phriend! Click me when something looks wrong."), 6000);
			this.storage_set(GREETED_KEY, "1");
		}
		this.refresh_badge();
	}

	storage_get(key) {
		try {
			return localStorage.getItem(key);
		} catch (e) {
			return null;
		}
	}

	storage_set(key, value) {
		try {
			localStorage.setItem(key, value);
		} catch (e) {
			// private mode etc.: not important
		}
	}

	// -------------------------------------------------------------- dragging

	restore_position() {
		const raw = this.storage_get(POS_KEY);
		if (!raw) return;
		try {
			const pos = JSON.parse(raw);
			this.set_position(pos.left, pos.top);
		} catch (e) {
			// ignore broken value
		}
	}

	set_position(left, top) {
		const w = this.root.offsetWidth || 64;
		const h = this.root.offsetHeight || 76;
		left = Math.max(4, Math.min(window.innerWidth - w - 4, left));
		top = Math.max(4, Math.min(window.innerHeight - h - 4, top));
		Object.assign(this.root.style, {
			left: `${left}px`,
			top: `${top}px`,
			right: "auto",
			bottom: "auto",
		});
		// keep the speech bubble on screen
		this.root.classList.toggle("phriend-flip", left < 260);
	}

	clamp_into_view() {
		if (!this.root.style.left) return;
		this.set_position(parseFloat(this.root.style.left), parseFloat(this.root.style.top));
	}

	setup_drag() {
		let start = null;
		let dragging = false;

		this.root.addEventListener("pointerdown", (e) => {
			if (e.button !== 0) return;
			const rect = this.root.getBoundingClientRect();
			start = { x: e.clientX, y: e.clientY, dx: e.clientX - rect.left, dy: e.clientY - rect.top };
			dragging = false;
			this.root.setPointerCapture(e.pointerId);
		});

		this.root.addEventListener("pointermove", (e) => {
			if (!start) return;
			if (!dragging && Math.hypot(e.clientX - start.x, e.clientY - start.y) > 5) {
				dragging = true;
				this.root.classList.add("phriend-dragging");
			}
			if (dragging) this.set_position(e.clientX - start.dx, e.clientY - start.dy);
		});

		this.root.addEventListener("pointerup", (e) => {
			if (!start) return;
			this.root.releasePointerCapture(e.pointerId);
			start = null;
			if (dragging) {
				this.root.classList.remove("phriend-dragging");
				this.storage_set(
					POS_KEY,
					JSON.stringify({
						left: parseFloat(this.root.style.left),
						top: parseFloat(this.root.style.top),
					})
				);
			} else {
				this.report();
			}
			dragging = false;
		});
	}

	// ------------------------------------------------------------ personality

	setup_eyes() {
		let frame = null;
		document.addEventListener("pointermove", (e) => {
			if (frame) return;
			frame = requestAnimationFrame(() => {
				frame = null;
				const rect = this.root.getBoundingClientRect();
				const cx = rect.left + rect.width / 2;
				const cy = rect.top + rect.height * 0.4;
				const angle = Math.atan2(e.clientY - cy, e.clientX - cx);
				const dist = Math.min(1, Math.hypot(e.clientX - cx, e.clientY - cy) / 200);
				const x = Math.cos(angle) * 2.2 * dist;
				const y = Math.sin(angle) * 2.8 * dist;
				this.pupils.forEach((p) => p.setAttribute("transform", `translate(${x} ${y})`));
			});
		});
	}

	hop() {
		this.root.classList.remove("phriend-hop");
		void this.root.offsetWidth; // restart animation
		this.root.classList.add("phriend-hop");
		setTimeout(() => this.root.classList.remove("phriend-hop"), 500);
	}

	say(html, ms = 4000) {
		clearTimeout(this._bubble_timer);
		this.$bubble.html(html).addClass("phriend-show");
		this._bubble_timer = setTimeout(() => this.$bubble.removeClass("phriend-show"), ms);
	}

	setup_shortcut() {
		frappe.ui.keys.add_shortcut({
			shortcut: "ctrl+shift+b",
			action: () => this.report(),
			description: __("Report an issue with Phriend"),
			ignore_inputs: true,
		});
	}

	// ------------------------------------------------------- error recording

	push(list, item) {
		list.push({ at: new Date().toISOString(), ...item });
		if (list.length > MAX_LOG) list.shift();
	}

	watch_errors() {
		window.addEventListener("error", (e) => {
			this.push(this.errors, {
				type: "error",
				message: String(e.message || e.error || "Unknown error"),
				source: e.filename ? `${e.filename}:${e.lineno}:${e.colno}` : undefined,
			});
		});

		window.addEventListener("unhandledrejection", (e) => {
			this.push(this.errors, {
				type: "unhandledrejection",
				message: String((e.reason && (e.reason.message || e.reason)) || "Unknown rejection"),
			});
		});

		const original_error = console.error;
		console.error = (...args) => {
			try {
				this.push(this.errors, {
					type: "console.error",
					message: args
						.map((a) => (a instanceof Error ? a.message : typeof a === "string" ? a : safe_json(a)))
						.join(" ")
						.slice(0, 1000),
				});
			} catch (e) {
				// never break console.error
			}
			return original_error.apply(console, args);
		};

		$(document).ajaxError((event, xhr, settings) => {
			let server_message;
			try {
				const body = JSON.parse(xhr.responseText || "{}");
				server_message = body.exception || body._error_message || body.message;
				if (!server_message && body._server_messages) {
					server_message = JSON.parse(body._server_messages)
						.map((m) => {
							try {
								return JSON.parse(m).message;
							} catch (e) {
								return m;
							}
						})
						.join(" | ");
				}
			} catch (e) {
				// not JSON
			}
			const method = (settings.data && extract_method(settings.data)) || "";
			this.push(this.failed_requests, {
				url: settings.url,
				method,
				status: xhr.status,
				message: server_message ? strip_html(String(server_message)).slice(0, 1000) : xhr.statusText,
			});
			if (this.$root && xhr.status >= 500) {
				this.say(
					__("Whoops, that call failed. <a class='phriend-report-link'>Report it?</a>"),
					6000
				);
				this.$bubble.find(".phriend-report-link").on("click", () => this.report());
			}
		});
	}

	// -------------------------------------------------------------- context

	page_context() {
		const route = frappe.get_route() || [];
		let ref_doctype = null;
		let ref_docname = null;
		let doc_info = null;

		if (route[0] === "Form" && window.cur_frm && cur_frm.doc) {
			ref_doctype = cur_frm.doctype;
			ref_docname = cur_frm.doc.__islocal ? null : cur_frm.docname;
			doc_info = {
				docstatus: cur_frm.doc.docstatus,
				is_new: !!cur_frm.doc.__islocal,
				is_dirty: !!cur_frm.is_dirty(),
				workflow_state: cur_frm.doc.workflow_state,
				status: cur_frm.doc.status,
			};
		} else if (["List", "Report", "Tree", "Kanban", "Calendar", "Gantt", "Dashboard"].includes(route[0])) {
			ref_doctype = route[1] || null;
		}

		const versions = {};
		Object.entries(frappe.boot.versions || {}).forEach(([app, v]) => (versions[app] = v));

		return {
			route: route.join("/"),
			page_url: window.location.href,
			page_title: document.title,
			ref_doctype,
			ref_docname,
			context: {
				captured_at: new Date().toISOString(),
				user: frappe.session.user,
				lang: frappe.boot.lang,
				site: frappe.boot.sitename,
				versions,
				route,
				doc: doc_info,
				viewport: `${window.innerWidth}x${window.innerHeight} @${window.devicePixelRatio}x`,
				user_agent: navigator.userAgent,
				recent_errors: this.errors.slice(),
				failed_requests: this.failed_requests.slice(),
			},
		};
	}

	// ------------------------------------------------------------ screenshot

	// The report dialog is already open while we capture, so everything Phriend
	// adds (the ball, its dialog, its backdrop) is marked and left out.
	is_excluded(el) {
		return (
			el.id === "phriend-root" ||
			el.id === "alert-container" ||
			(el.classList &&
				["phriend-ignore", "sr-only", "visually-hidden"].some((c) => el.classList.contains(c))) ||
			(el.getAttribute && el.getAttribute("role") === "status" && el.hasAttribute("aria-live"))
		);
	}

	// Skip anything that can't be in the screenshot: hidden (Frappe keeps every
	// page you visited in the DOM, display:none), the icon sprite, and anything
	// entirely outside the window. Copying those was ~90% of the capture time.
	is_off_screen(el) {
		if (!el.getBoundingClientRect || el === document.body || el === document.documentElement) return false;
		if (KEEP_TAGS.has(el.tagName) || el.parentNode === document.head) return false; // the page's CSS
		const r = el.getBoundingClientRect();
		if (r.width === 0 && r.height === 0) {
			// display:none subtree, or the 0x0 <svg> holding Frappe's icon symbols
			return el.tagName.toLowerCase() === "svg" || getComputedStyle(el).display === "none";
		}
		const outside = r.bottom < 0 || r.top > window.innerHeight || r.right < 0 || r.left > window.innerWidth;
		// an off-screen wrapper might still hold an open (fixed) dialog
		return outside && !el.querySelector(".modal.show, .modal-backdrop");
	}

	async capture(engine_key) {
		this.root.classList.add("phriend-hidden");
		// Frappe draws pseudo-elements (::after) on grid checkboxes. html2canvas
		// tries to copy them into the <input>, reads an empty style and crashes
		// with "Error parsing CSS component value". Switch them off while we draw.
		const fix = document.createElement("style");
		fix.id = "phriend-capture-fix";
		fix.textContent =
			"input::before,input::after,textarea::before,textarea::after," +
			"select::before,select::after{content:none!important}";
		document.head.appendChild(fix);
		// let the browser apply that before we render (a timer, not
		// requestAnimationFrame: that pauses while the tab is in the background)
		await sleep(60);
		try {
			return await with_timeout(this.render(engine_key), CAPTURE_TIMEOUT_MS);
		} finally {
			fix.remove();
			this.root.classList.remove("phriend-hidden");
		}
	}

	async render(engine_key) {
		// html2canvas re-implements CSS and chokes on some pages ("Error parsing
		// CSS component value"), after several seconds of work. html-to-image lets
		// the browser render instead. Remember per DocType which one works so the
		// slow failure only happens once.
		const memo = `${ENGINE_KEY_PREFIX}${engine_key}`;
		if (this.storage_get(memo) === "html-to-image") {
			return await this.render_html_to_image();
		}
		try {
			return await with_timeout(this.render_html2canvas(), HTML2CANVAS_TIMEOUT_MS);
		} catch (e) {
			console.warn("Phriend: html2canvas failed, trying html-to-image", e);
			this.storage_set(memo, "html-to-image");
			return await this.render_html_to_image();
		}
	}

	render_html_to_image() {
		const skip = (node) => !(this.is_excluded(node) || this.is_off_screen(node));
		return html_to_canvas(document.body, {
			width: window.innerWidth,
			height: window.innerHeight,
			pixelRatio: 1, // 2x is ~4x the work and freezes heavy pages
			skipFonts: true, // embedding every web font is the slowest part
			backgroundColor: getComputedStyle(document.body).backgroundColor || "#fff",
			filter: skip,
			imagePlaceholder:
				"data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7",
			style: {
				// show the part of the page that is on screen
				transform: `translate(${-window.scrollX}px, ${-window.scrollY}px)`,
				transformOrigin: "0 0",
			},
		});
	}

	render_html2canvas() {
		return html2canvas(document.body, {
			logging: !!this.storage_get(DEBUG_KEY),
			x: window.scrollX,
			y: window.scrollY,
			width: window.innerWidth,
			height: window.innerHeight,
			windowWidth: window.innerWidth,
			windowHeight: window.innerHeight,
			scale: 1, // 2x is ~4x the work and freezes heavy pages
			useCORS: true,
			imageTimeout: 1500, // don't hang on a slow avatar
			backgroundColor: getComputedStyle(document.body).backgroundColor || "#fff",
			// leave out Phriend itself, its dialog, toast alerts and screen-reader-only
			// text (html2canvas ignores CSS clip, so that text would show up)
			ignoreElements: (el) => this.is_excluded(el) || this.is_off_screen(el),
		});
	}

	// ----------------------------------------------------------------- report

	async report() {
		if (this.busy) return;
		if (document.querySelector(".modal.show .phriend-annotator")) return;
		this.busy = true;
		this.hop();
		this.root.classList.add("phriend-busy");

		const ctx = this.page_context();

		// mark backdrops that exist now as "page"; the one our dialog adds is ours
		const old_backdrops = new Set(document.querySelectorAll(".modal-backdrop"));
		const dialog = this.open_dialog(ctx);
		const ours = () =>
			document.querySelectorAll(".modal-backdrop").forEach((b) => {
				if (!old_backdrops.has(b)) b.classList.add("phriend-ignore");
			});
		dialog.$wrapper.addClass("phriend-ignore");
		ours();

		// Capture behind the open dialog: the user can start typing right away.
		// Rendering the page blocks the browser for a moment, so first let the
		// dialog finish appearing, otherwise you only see the dimmed backdrop.
		dialog.phriend_capture = (async () => {
			try {
				await dialog_shown(dialog);
				ours();
				const canvas = await this.capture(ctx.ref_doctype || ctx.route.split("/")[0] || "page");
				dialog.phriend_annotator = new Annotator(dialog.fields_dict.annotator.$wrapper, canvas);
			} catch (e) {
				console.warn("Phriend could not take a screenshot", e);
				dialog.fields_dict.annotator.$wrapper.html(
					`<p class="text-muted">${__(
						"I couldn't take a screenshot this time, but you can still describe it."
					)}</p>`
				);
			} finally {
				this.root.classList.remove("phriend-busy");
				this.busy = false;
			}
		})();
	}

	open_dialog(ctx) {
		const where = ctx.ref_docname
			? `${__(ctx.ref_doctype)} ${ctx.ref_docname}`
			: ctx.ref_doctype
			? __(ctx.ref_doctype)
			: ctx.page_title;

		const dialog = new frappe.ui.Dialog({
			title: __("Phriend: report an issue"),
			size: "extra-large",
			fields: [
				{ fieldtype: "HTML", fieldname: "annotator" },
				{ fieldtype: "Section Break" },
				{
					fieldtype: "Data",
					fieldname: "title",
					label: __("Title"),
					reqd: 1,
					default: "",
					description: __("Reported on: {0}", [frappe.utils.escape_html(where || "")]),
				},
				{ fieldtype: "Column Break" },
				{
					fieldtype: "Select",
					fieldname: "report_type",
					label: __("Type"),
					options: ["Bug", "Idea", "Question"],
					default: "Bug",
				},
				{ fieldtype: "Column Break" },
				{
					fieldtype: "Select",
					fieldname: "priority",
					label: __("Priority"),
					options: ["Low", "Medium", "High", "Urgent"],
					default: "Medium",
				},
				{ fieldtype: "Section Break" },
				{
					fieldtype: "Small Text",
					fieldname: "comment",
					label: __("What happened? What did you expect?"),
				},
				{
					fieldtype: "Section Break",
					label: __("Captured context"),
					collapsible: 1,
				},
				{
					fieldtype: "Code",
					fieldname: "context",
					options: "JSON",
					read_only: 1,
					default: JSON.stringify(
						{ route: ctx.route, ref_doctype: ctx.ref_doctype, ref_docname: ctx.ref_docname, ...ctx.context },
						null,
						2
					),
				},
			],
			primary_action_label: __("Send to Phriend"),
			primary_action: (values) => this.submit(dialog, ctx, values),
		});

		dialog.fields_dict.annotator.$wrapper.html(
			`<div class="phriend-capturing text-muted">
				<span class="phriend-spinner"></span>
				${__("Taking a screenshot of the page… you can start typing.")}
			</div>`
		);
		dialog.onhide = () => this.root.classList.remove("phriend-away");
		dialog.show();
		this.root.classList.add("phriend-away");
		setTimeout(() => dialog.fields_dict.title.$input.focus(), 300);
		return dialog;
	}

	async submit(dialog, ctx, values) {
		dialog.disable_primary_action();
		if (dialog.phriend_capture) {
			// still capturing? wait for it rather than sending without a screenshot
			frappe.dom.freeze(__("Finishing the screenshot…"));
			try {
				await dialog.phriend_capture;
			} finally {
				frappe.dom.unfreeze();
			}
		}
		const annotator = dialog.phriend_annotator;
		frappe.call({
			method: "phamos.phriend.api.create_report",
			args: {
				title: values.title,
				comment: values.comment || "",
				report_type: values.report_type,
				priority: values.priority,
				route: ctx.route,
				page_url: ctx.page_url,
				ref_doctype: ctx.ref_doctype,
				ref_docname: ctx.ref_docname,
				context: JSON.stringify(ctx.context),
				screenshot: annotator ? annotator.to_data_url() : null,
			},
			freeze: true,
			freeze_message: __("Phriend is writing it down..."),
			callback: (r) => {
				if (!r.message) return;
				dialog.hide();
				const link = `<a href="/app/issue/${encodeURIComponent(r.message.name)}">${r.message.name}</a>`;
				this.hop();
				this.say(__("Got it! Saved as {0} 🎉", [link]), 6000);
				frappe.show_alert({ message: __("Issue {0} created", [link]), indicator: "green" }, 6);
				this.refresh_badge();
			},
			always: () => dialog.enable_primary_action(),
		});
	}

	// ------------------------------------------------------------ the badge

	badge_filters() {
		const route = frappe.get_route() || [];
		const filters = { phriend_type: ["is", "set"], status: ["not in", CLOSED_STATUSES] };
		if (route[0] === "Form" && route[2]) {
			filters.phriend_ref_doctype = route[1];
			filters.phriend_ref_docname = route[2];
		} else if (route[0] && route[1] && route[0] !== "Workspaces") {
			filters.phriend_ref_doctype = route[1];
		} else {
			filters.phriend_route = route.join("/");
		}
		return filters;
	}

	refresh_badge() {
		if (!frappe.model.can_read(REPORT_DOCTYPE)) return;
		clearTimeout(this._badge_timer);
		this._badge_timer = setTimeout(() => {
			frappe.db
				.count(REPORT_DOCTYPE, { filters: this.badge_filters() })
				.then((count) => {
					this.$badge.attr("data-count", count || 0).text(count ? String(count) : "");
					this.$badge.attr("title", __("{0} open Phriend reports for this page", [count]));
				})
				.catch(() => {});
		}, 400);
	}

	open_reports_for_page() {
		const filters = this.badge_filters();
		frappe.route_options = {};
		Object.entries(filters).forEach(([k, v]) => {
			if (k === "phriend_ref_doctype" || k === "phriend_ref_docname" || k === "phriend_route") {
				frappe.route_options[k] = v;
			}
		});
		frappe.route_options.phriend_type = ["is", "set"];
		frappe.route_options.status = ["not in", CLOSED_STATUSES];
		frappe.set_route("List", REPORT_DOCTYPE);
	}

	setup_route_watch() {
		if (frappe.router && typeof frappe.router.on === "function") {
			frappe.router.on("change", () => this.refresh_badge());
		} else {
			$(window).on("hashchange popstate", () => this.refresh_badge());
		}
	}
}

// ------------------------------------------------------------------ annotate

class Annotator {
	constructor($wrapper, screenshot) {
		this.base = screenshot;
		this.shapes = [];
		this.tool = "pen";

		$wrapper.html(`
			<div class="phriend-annotator">
				<div class="phriend-toolbar">
					<button type="button" class="btn btn-xs btn-default active" data-tool="pen">✏️ ${__("Pen")}</button>
					<button type="button" class="btn btn-xs btn-default" data-tool="box">▭ ${__("Box")}</button>
					<button type="button" class="btn btn-xs btn-default" data-tool="text">T ${__("Text")}</button>
					<button type="button" class="btn btn-xs btn-default" data-action="undo">↶ ${__("Undo")}</button>
					<button type="button" class="btn btn-xs btn-default" data-action="clear">${__("Clear")}</button>
					<span class="phriend-hint">${__("Drag an arrow to the problem, box it, or click Text and type on it")}</span>
				</div>
				<div class="phriend-canvas-wrap"><canvas></canvas></div>
			</div>
		`);

		this.canvas = $wrapper.find("canvas").get(0);
		this.canvas.width = screenshot.width;
		this.canvas.height = screenshot.height;
		this.ctx = this.canvas.getContext("2d");

		this.wrap = $wrapper.find(".phriend-canvas-wrap").get(0);

		$wrapper.find("[data-tool]").on("click", (e) => {
			this.commit_text();
			this.tool = e.currentTarget.dataset.tool;
			this.canvas.style.cursor = this.tool === "text" ? "text" : "crosshair";
			$wrapper.find("[data-tool]").removeClass("active");
			$(e.currentTarget).addClass("active");
		});
		$wrapper.find("[data-action=undo]").on("click", () => {
			if (this.cancel_text()) return; // undo the text box you're typing in first
			this.shapes.pop();
			this.redraw();
		});
		$wrapper.find("[data-action=clear]").on("click", () => {
			this.cancel_text();
			this.shapes = [];
			this.redraw();
		});

		this.bind_drawing();
		this.redraw();
	}

	point(e) {
		const rect = this.canvas.getBoundingClientRect();
		return {
			x: ((e.clientX - rect.left) / rect.width) * this.canvas.width,
			y: ((e.clientY - rect.top) / rect.height) * this.canvas.height,
		};
	}

	// canvas pixels per on-screen pixel (the screenshot is shown scaled down)
	scale() {
		const rect = this.canvas.getBoundingClientRect();
		return this.canvas.width / (rect.width || this.canvas.width);
	}

	line_width() {
		return 4 * this.scale();
	}

	bind_drawing() {
		let current = null;
		this.canvas.addEventListener("pointerdown", (e) => {
			if (this.tool === "text") {
				e.preventDefault(); // keep focus for the text box we're about to open
				this.commit_text();
				this.start_text(e);
				return;
			}
			this.canvas.setPointerCapture(e.pointerId);
			const p = this.point(e);
			current =
				this.tool === "box"
					? { type: "box", x1: p.x, y1: p.y, x2: p.x, y2: p.y, w: this.line_width() }
					: { type: "pen", points: [p, { ...p }], w: this.line_width() }; // straight arrow
			this.shapes.push(current);
		});
		this.canvas.addEventListener("pointermove", (e) => {
			if (!current) return;
			const p = this.point(e);
			if (current.type === "box") {
				current.x2 = p.x;
				current.y2 = p.y;
			} else {
				current.points[1] = p;
			}
			this.redraw();
		});
		const stop = () => {
			// a click without dragging leaves nothing behind
			if (current && this.size_of(current) < current.w * 2) {
				this.shapes.pop();
				this.redraw();
			}
			current = null;
		};
		this.canvas.addEventListener("pointerup", stop);
		this.canvas.addEventListener("pointercancel", stop);
	}

	size_of(s) {
		if (s.type === "box") return Math.max(Math.abs(s.x2 - s.x1), Math.abs(s.y2 - s.y1));
		const [a, b] = s.points;
		return Math.hypot(b.x - a.x, b.y - a.y);
	}

	// ---- text: click on the screenshot, type, Enter (or click away) to place it

	font(size) {
		return `600 ${size}px -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, sans-serif`;
	}

	start_text(e) {
		const rect = this.canvas.getBoundingClientRect();
		const x = e.clientX - rect.left;
		const y = e.clientY - rect.top;
		const input = document.createElement("input");
		input.type = "text";
		input.className = "phriend-text-input";
		input.placeholder = __("Type here…");
		input.style.left = `${this.canvas.offsetLeft + x}px`;
		input.style.top = `${this.canvas.offsetTop + y}px`;
		this.wrap.appendChild(input);
		this.editing = { input, x: x * this.scale(), y: y * this.scale() };

		input.addEventListener("keydown", (ev) => {
			// keep Enter / Escape away from the dialog (Escape would close it)
			ev.stopPropagation();
			if (ev.key === "Enter") {
				ev.preventDefault();
				this.commit_text();
			} else if (ev.key === "Escape") {
				ev.preventDefault();
				this.cancel_text();
			}
		});
		input.addEventListener("blur", () => this.commit_text());
		setTimeout(() => input.focus(), 0);
	}

	commit_text() {
		const editing = this.editing;
		if (!editing) return;
		this.editing = null;
		const text = editing.input.value.trim();
		editing.input.remove();
		if (!text) return;
		const scale = this.scale();
		this.shapes.push({ type: "text", x: editing.x, y: editing.y, text, size: 18 * scale, w: 4 * scale });
		this.redraw();
	}

	cancel_text() {
		if (!this.editing) return false;
		const { input } = this.editing;
		this.editing = null;
		input.remove();
		return true;
	}

	redraw() {
		const ctx = this.ctx;
		ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
		ctx.drawImage(this.base, 0, 0);
		ctx.strokeStyle = "#e5222b";
		ctx.lineCap = "round";
		ctx.lineJoin = "round";
		this.shapes.forEach((s) => {
			ctx.lineWidth = s.w;
			if (s.type === "text") {
				this.draw_text(s);
			} else if (s.type === "box") {
				ctx.strokeRect(
					Math.min(s.x1, s.x2),
					Math.min(s.y1, s.y2),
					Math.abs(s.x2 - s.x1),
					Math.abs(s.y2 - s.y1)
				);
			} else {
				ctx.beginPath();
				s.points.forEach((p, i) => (i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y)));
				ctx.stroke();
				this.arrow_head(s);
			}
		});
	}

	// red text on a white label so it reads on any background
	draw_text(s) {
		const ctx = this.ctx;
		ctx.save();
		ctx.font = this.font(s.size);
		ctx.textBaseline = "top";
		const pad = s.size * 0.3;
		const width = ctx.measureText(s.text).width;
		ctx.fillStyle = "rgba(255, 255, 255, 0.92)";
		ctx.fillRect(s.x - pad, s.y - pad, width + pad * 2, s.size * 1.2 + pad * 2);
		ctx.lineWidth = s.w / 2;
		ctx.strokeRect(s.x - pad, s.y - pad, width + pad * 2, s.size * 1.2 + pad * 2);
		ctx.fillStyle = ctx.strokeStyle;
		ctx.fillText(s.text, s.x, s.y + s.size * 0.1);
		ctx.restore();
	}

	// The pen draws a straight arrow from where you press to where you let go.
	arrow_head(s) {
		const [from, tip] = s.points;
		if (from.x === tip.x && from.y === tip.y) return;
		const a = Math.atan2(tip.y - from.y, tip.x - from.x);
		const len = s.w * 4.5;
		const spread = Math.PI / 7;
		const ctx = this.ctx;
		const x = tip.x + Math.cos(a) * s.w * 0.5; // cover the round line cap
		const y = tip.y + Math.sin(a) * s.w * 0.5;
		ctx.beginPath();
		ctx.moveTo(x, y);
		ctx.lineTo(x - len * Math.cos(a - spread), y - len * Math.sin(a - spread));
		ctx.lineTo(x - len * Math.cos(a + spread), y - len * Math.sin(a + spread));
		ctx.closePath();
		ctx.fillStyle = ctx.strokeStyle;
		ctx.fill();
	}

	to_data_url() {
		this.commit_text(); // still typing when Send was clicked
		return this.canvas.toDataURL("image/png");
	}
}

// ------------------------------------------------------------------- helpers

function sleep(ms) {
	return new Promise((r) => setTimeout(r, ms));
}

function dialog_shown(dialog) {
	return new Promise((resolve) => {
		let done = false;
		const finish = () => {
			if (done) return;
			done = true;
			// give the browser time to paint the dialog (timer, not
			// requestAnimationFrame, which pauses in background tabs)
			setTimeout(resolve, 80);
		};
		if (dialog.$wrapper.hasClass("show") && dialog.$wrapper.is(":visible")) {
			setTimeout(finish, 350); // fade-in still running
		}
		dialog.$wrapper.one("shown.bs.modal", finish);
		setTimeout(finish, 800); // safety net
	});
}

function with_timeout(promise, ms) {
	return new Promise((resolve, reject) => {
		const timer = setTimeout(() => reject(new Error(`Screenshot timed out after ${ms} ms`)), ms);
		promise.then(
			(v) => {
				clearTimeout(timer);
				resolve(v);
			},
			(e) => {
				clearTimeout(timer);
				reject(e);
			}
		);
	});
}

function safe_json(value) {
	try {
		return JSON.stringify(value);
	} catch (e) {
		return String(value);
	}
}

function strip_html(text) {
	const div = document.createElement("div");
	div.innerHTML = text;
	return div.textContent || div.innerText || "";
}

function extract_method(data) {
	if (typeof data !== "string") return data && data.cmd;
	const match = data.match(/(?:^|&)cmd=([^&]+)/);
	return match ? decodeURIComponent(match[1]) : "";
}

// ------------------------------------------------------------------- boot

frappe.provide("phriend");
phriend.instance = new Phriend(); // start recording errors as early as possible
// handy for debugging captures from the console
phriend.html2canvas = html2canvas;
phriend.html_to_canvas = html_to_canvas;

$(document).ready(() => {
	if (!frappe.boot || !frappe.boot.phriend || !frappe.boot.phriend.enabled) return;
	if (frappe.session.user === "Guest") return;
	phriend.instance.mount();
});
