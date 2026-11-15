// The ball itself: a black ball with legs, drawn once into a Shadow DOM so Bootstrap (Desk)
// and Tailwind (cockpits) can't change how it looks. This module is loaded on every page,
// so it stays small: the capture and the report flow load on demand (flow.js).

import { escape_html, host_theme, storage_get, storage_set } from "./util";

const POS_KEY = "phriend:position";

export const SVG = `
<svg viewBox="0 0 64 76" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
	<defs>
		<radialGradient id="phriend-grad" cx="35%" cy="30%" r="75%">
			<stop offset="0%" stop-color="#4a4a4a"/>
			<stop offset="45%" stop-color="#151515"/>
			<stop offset="100%" stop-color="#000"/>
		</radialGradient>
	</defs>
	<ellipse class="shadow" cx="32" cy="72" rx="16" ry="3" fill="#000" opacity="0.25"/>
	<g class="body">
		<g class="leg leg-l">
			<path d="M24 48 L20 66" stroke="#111" stroke-width="4" stroke-linecap="round"/>
			<ellipse cx="17.5" cy="67" rx="5.5" ry="2.6" fill="#111"/>
		</g>
		<g class="leg leg-r">
			<path d="M40 48 L44 66" stroke="#111" stroke-width="4" stroke-linecap="round"/>
			<ellipse cx="46.5" cy="67" rx="5.5" ry="2.6" fill="#111"/>
		</g>
		<circle class="sphere" cx="32" cy="32" r="24" fill="url(#phriend-grad)"/>
		<ellipse cx="23" cy="20" rx="6" ry="3.5" fill="#fff" opacity="0.16" transform="rotate(-30 23 20)"/>
		<g class="eyes">
			<ellipse cx="24" cy="30" rx="5.5" ry="6.5" fill="#fff"/>
			<ellipse cx="40" cy="30" rx="5.5" ry="6.5" fill="#fff"/>
			<circle class="pupil" cx="24" cy="31" r="2.8" fill="#111"/>
			<circle class="pupil" cx="40" cy="31" r="2.8" fill="#111"/>
		</g>
		<path d="M27 42 Q32 46.5 37 42" stroke="#fff" stroke-width="1.8" fill="none" stroke-linecap="round" opacity="0.85"/>
	</g>
</svg>`;

// Colours and type for everything inside the Shadow DOM (the flow adds its own rules).
const BASE_CSS = `
:host {
	all: initial;
	--ph-bg: #ffffff; --ph-surface: #f7f7f8; --ph-text: #171717; --ph-muted: #6b6b6b;
	--ph-border: rgba(0, 0, 0, 0.12); --ph-border-strong: rgba(0, 0, 0, 0.22);
	--ph-accent: #171717; --ph-on-accent: #ffffff; --ph-focus: #2f6fdb;
	--ph-chip: #eef3fd; --ph-chip-text: #1d4ea3; --ph-chip-border: #a9c2f0;
	--ph-danger: #c62f2f; --ph-success: #23824a; --ph-red: #e5222b;
	--ph-shadow: 0 12px 40px rgba(0, 0, 0, 0.18), 0 2px 8px rgba(0, 0, 0, 0.08);
	--ph-font: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
	position: fixed; top: 0; left: 0; width: 0; height: 0; z-index: 1056;
	font-family: var(--ph-font); font-size: 14px; line-height: 1.45; color: var(--ph-text);
}
:host([data-theme="dark"]) {
	--ph-bg: #1f1f1f; --ph-surface: #2a2a2a; --ph-text: #f2f2f2; --ph-muted: #a3a3a3;
	--ph-border: rgba(255, 255, 255, 0.12); --ph-border-strong: rgba(255, 255, 255, 0.24);
	--ph-accent: #f2f2f2; --ph-on-accent: #171717; --ph-focus: #7aa7f5;
	--ph-chip: #1c2c4a; --ph-chip-text: #b9cff7; --ph-chip-border: #3a5a96;
	--ph-danger: #f08a8a; --ph-success: #7ccf9b;
	--ph-shadow: 0 12px 40px rgba(0, 0, 0, 0.5);
}
* { box-sizing: border-box; }
a { color: inherit; text-decoration: underline; cursor: pointer; }
.ball {
	position: fixed; right: 24px; bottom: 24px; width: 64px; height: 76px;
	user-select: none; -webkit-user-select: none;
}
.hit { width: 100%; height: 100%; touch-action: none; cursor: grab; outline: none; }
.ball.dragging .hit { cursor: grabbing; }
.ball.away { display: none; }
.hit:focus-visible svg { outline: 2px solid var(--ph-focus); outline-offset: 2px; border-radius: 50%; }
button.link { padding: 0; border: 0; background: none; color: inherit; font: inherit; text-decoration: underline; cursor: pointer; }
button.link:focus-visible, .bubble a:focus-visible { outline: 2px solid var(--ph-focus); outline-offset: 1px; border-radius: 2px; }
.ball svg { width: 100%; height: 100%; overflow: visible; display: block; filter: drop-shadow(0 4px 6px rgba(0, 0, 0, 0.25)); }
:host([data-theme="dark"]) .sphere { stroke: rgba(255, 255, 255, 0.35); stroke-width: 1.5; }
/* Box breathing, one 21 s cycle: in 4 s, hold 5 s, out 7 s, hold 5 s. The ball fills up from
   its feet while breathing in and settles while breathing out; the shadow follows. */
.body { transform-box: fill-box; transform-origin: 50% 100%; animation: breathe 21s infinite; }
.shadow { transform-box: fill-box; transform-origin: center; animation: breathe-shadow 21s infinite; }
.eyes { transform-box: fill-box; transform-origin: center; animation: blink 5s infinite; }
.pupil { transition: transform 0.08s linear; }
.leg { transform-box: fill-box; transform-origin: 50% 0%; }
.ball:hover .leg-l { animation: wiggle-l 0.35s ease-in-out infinite alternate; }
.ball:hover .leg-r { animation: wiggle-r 0.35s ease-in-out infinite alternate; }
.ball.hop .body { animation: hop 0.45s ease-out 1; }
.ball.busy .eyes { animation: squint 0.6s ease-in-out infinite alternate; }
:host([data-paused]) * { animation-play-state: paused !important; }
@media (prefers-reduced-motion: reduce) {
	.body, .shadow, .eyes, .ball:hover .leg-l, .ball:hover .leg-r, .ball.busy .eyes { animation: none; }
	.ball.hop .body { animation: none; }
}
.badge {
	position: absolute; top: -2px; right: -2px; border: 0; font-family: inherit; min-width: 20px; height: 20px; padding: 0 5px;
	border-radius: 10px; background: #e03636; color: #fff; font-size: 11px; font-weight: 600;
	line-height: 20px; text-align: center; cursor: pointer; box-shadow: 0 0 0 2px var(--ph-bg);
}
.badge:empty { display: none; }
.pending { position: absolute; left: -2px; top: -2px; width: 12px; height: 12px; border-radius: 50%;
	background: #e8a23a; box-shadow: 0 0 0 2px var(--ph-bg); display: none; }
.ball.has-pending .pending { display: block; }
.bubble {
	position: absolute; bottom: calc(100% + 8px); right: 0; width: max-content; max-width: 260px;
	padding: 8px 12px; border-radius: 12px; background: var(--ph-bg); color: var(--ph-text);
	border: 1px solid var(--ph-border); box-shadow: var(--ph-shadow); font-size: 13px; line-height: 1.4;
	opacity: 0; transform: translateY(6px); transition: opacity 0.2s, transform 0.2s; pointer-events: none; cursor: auto;
}
.bubble.show { opacity: 1; transform: translateY(0); pointer-events: auto; }
.bubble::after { content: ""; position: absolute; top: 100%; right: 22px; border: 7px solid transparent; border-top-color: var(--ph-bg); }
.ball.flip .bubble { right: auto; left: 0; }
.ball.flip .bubble::after { right: auto; left: 22px; }
/* 4 / 21 = 19.05 %, 9 / 21 = 42.86 %, 16 / 21 = 76.19 % */
@keyframes breathe {
	0% { transform: scale(1, 1); animation-timing-function: ease-in-out; }
	19.05% { transform: scale(1.07, 1.09); }
	42.86% { transform: scale(1.07, 1.09); animation-timing-function: ease-in-out; }
	76.19% { transform: scale(1, 1); }
	100% { transform: scale(1, 1); }
}
@keyframes breathe-shadow {
	0% { transform: scaleX(1); opacity: 0.25; animation-timing-function: ease-in-out; }
	19.05% { transform: scaleX(1.12); opacity: 0.3; }
	42.86% { transform: scaleX(1.12); opacity: 0.3; animation-timing-function: ease-in-out; }
	76.19% { transform: scaleX(1); opacity: 0.25; }
	100% { transform: scaleX(1); opacity: 0.25; }
}
@keyframes blink { 0%, 94%, 100% { transform: scaleY(1); } 96% { transform: scaleY(0.1); } }
@keyframes squint { from { transform: scaleY(1); } to { transform: scaleY(0.45); } }
@keyframes wiggle-l { from { transform: rotate(-12deg); } to { transform: rotate(10deg); } }
@keyframes wiggle-r { from { transform: rotate(12deg); } to { transform: rotate(-10deg); } }
@keyframes hop { 0% { transform: translateY(0); } 35% { transform: translateY(-14px); } 70% { transform: translateY(0); } 85% { transform: translateY(-3px); } 100% { transform: translateY(0); } }
`;

export class Ball {
	// options: { label, on_click, on_badge_click, on_first_interest, start }
	// start: { right, bottom } in px until the user drags the ball (the cockpits keep it clear
	// of their own buttons in the corner)
	constructor(options) {
		this.options = options;
		this.host = document.createElement("div");
		this.host.id = "phriend-root"; // left out of every screenshot (capture.js)
		this.shadow = this.host.attachShadow({ mode: "open" });
		this.shadow.innerHTML = `
			<style>${BASE_CSS}</style>
			<div class="ball">
				<div class="bubble" role="status" aria-live="polite"></div>
				<div class="hit" role="button" tabindex="0" aria-label="${escape_html(options.label)}" title="${escape_html(options.label)}">${SVG}</div>
				<span class="pending"></span>
				<button type="button" class="badge"></button>
			</div>
			<div class="layer"></div>`;
		document.body.appendChild(this.host);

		this.root = this.shadow.querySelector(".ball");
		this.hit = this.shadow.querySelector(".hit"); // the ball itself: drag, click, keyboard
		this.bubble = this.shadow.querySelector(".bubble");
		this.badge = this.shadow.querySelector(".badge");
		this.layer = this.shadow.querySelector(".layer"); // the report flow mounts here
		this.pupils = this.shadow.querySelectorAll(".pupil");

		this.sync_theme();
		if (options.start) {
			this.root.style.right = `${options.start.right}px`;
			this.root.style.bottom = `${options.start.bottom}px`;
		}
		this.restore_position();
		this.setup_drag();
		this.setup_eyes();
		this.setup_interest();
		this.setup_pause();

		this.badge.addEventListener("pointerdown", (e) => e.stopPropagation());
		this.badge.addEventListener("click", (e) => {
			e.stopPropagation();
			options.on_badge_click && options.on_badge_click();
		});
		this.bubble.addEventListener("pointerdown", (e) => e.stopPropagation());
		this.hit.addEventListener("keydown", (e) => {
			if (e.key === "Enter" || e.key === " ") {
				e.preventDefault();
				options.on_click();
			}
		});
		window.addEventListener("resize", () => this.clamp_into_view());
	}

	// ---- theme and idle cost

	sync_theme() {
		const apply = () => this.host.setAttribute("data-theme", host_theme());
		apply();
		new MutationObserver(apply).observe(document.documentElement, {
			attributes: true,
			attributeFilter: ["data-theme"],
		});
	}

	setup_pause() {
		// no animation work at all while the tab is in the background
		const apply = () => this.host.toggleAttribute("data-paused", document.hidden);
		document.addEventListener("visibilitychange", apply);
		apply();
	}

	// Load the report flow before it is needed: the first hover or keyboard focus.
	setup_interest() {
		const once = () => {
			this.hit.removeEventListener("pointerenter", once);
			this.hit.removeEventListener("focus", once);
			this.options.on_first_interest && this.options.on_first_interest();
		};
		this.hit.addEventListener("pointerenter", once);
		this.hit.addEventListener("focus", once);
	}

	// ---- position and dragging

	restore_position() {
		try {
			const pos = JSON.parse(storage_get(POS_KEY) || "null");
			if (pos) this.set_position(pos.left, pos.top);
		} catch (e) {
			// ignore a broken value
		}
	}

	set_position(left, top) {
		const w = this.root.offsetWidth || 64;
		const h = this.root.offsetHeight || 76;
		left = Math.max(4, Math.min(window.innerWidth - w - 4, left));
		top = Math.max(4, Math.min(window.innerHeight - h - 4, top));
		Object.assign(this.root.style, { left: `${left}px`, top: `${top}px`, right: "auto", bottom: "auto" });
		this.root.classList.toggle("flip", left < 260); // keep the speech bubble on screen
	}

	clamp_into_view() {
		if (!this.root.style.left) return;
		this.set_position(parseFloat(this.root.style.left), parseFloat(this.root.style.top));
	}

	setup_drag() {
		let start = null;
		let dragging = false;

		this.hit.addEventListener("pointerdown", (e) => {
			if (e.button !== 0) return;
			const rect = this.root.getBoundingClientRect();
			start = { x: e.clientX, y: e.clientY, dx: e.clientX - rect.left, dy: e.clientY - rect.top };
			dragging = false;
			this.hit.setPointerCapture(e.pointerId);
		});

		this.hit.addEventListener("pointermove", (e) => {
			if (!start) return;
			if (!dragging && Math.hypot(e.clientX - start.x, e.clientY - start.y) > 5) {
				dragging = true;
				this.root.classList.add("dragging");
			}
			if (dragging) this.set_position(e.clientX - start.dx, e.clientY - start.dy);
		});

		const end = (e, cancelled) => {
			if (!start) return;
			this.hit.releasePointerCapture(e.pointerId);
			start = null;
			if (dragging) {
				this.root.classList.remove("dragging");
				storage_set(
					POS_KEY,
					JSON.stringify({ left: parseFloat(this.root.style.left), top: parseFloat(this.root.style.top) })
				);
			} else if (!cancelled) {
				this.options.on_click();
			}
			dragging = false;
		};
		this.hit.addEventListener("pointerup", (e) => end(e, false));
		this.hit.addEventListener("pointercancel", (e) => end(e, true));
	}

	// ---- personality

	setup_eyes() {
		let frame = null;
		document.addEventListener(
			"pointermove",
			(e) => {
				if (frame || document.hidden) return;
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
			},
			{ passive: true }
		);
	}

	hop() {
		this.root.classList.remove("hop");
		void this.root.offsetWidth; // restart the animation
		this.root.classList.add("hop");
		setTimeout(() => this.root.classList.remove("hop"), 500);
	}

	set_busy(busy) {
		this.root.classList.toggle("busy", !!busy);
	}

	set_away(away) {
		this.root.classList.toggle("away", !!away);
	}

	set_pending(pending) {
		this.root.classList.toggle("has-pending", !!pending);
	}

	// html: trusted markup built by Phriend itself (user text is escaped by the caller).
	// ms = 0 keeps the bubble until the next say() or hide_bubble().
	say(html, ms = 4000) {
		clearTimeout(this._bubble_timer);
		this.bubble.innerHTML = html;
		this.bubble.classList.add("show");
		if (ms) this._bubble_timer = setTimeout(() => this.hide_bubble(), ms);
		return this.bubble;
	}

	hide_bubble() {
		clearTimeout(this._bubble_timer);
		this.bubble.classList.remove("show");
	}

	set_label(label) {
		this.hit.setAttribute("aria-label", label);
		this.hit.title = label;
	}

	set_badge(count, title) {
		this.badge.textContent = count ? String(count) : "";
		this.badge.title = title || "";
		this.badge.setAttribute("aria-label", title || "");
	}
}
