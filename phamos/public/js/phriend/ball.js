// The ball itself: a black ball with legs, drawn once into a Shadow DOM so Bootstrap (Desk)
// and Tailwind (cockpits) can't change how it looks. This module is loaded on every page,
// so it stays small: the capture and the report flow load on demand (flow.js).

import { escape_html, host_theme, storage_get, storage_set, watch_theme } from "./util";

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

// The hand that goes with a bubble (#1990), say(html, ms, "<gesture>"), and the reactions
// without words, react("<gesture>") (#2009). The system's own emoji, default skin tone, so they
// look like the emoji people know on their device (PM, 2026-11-21). The motion names a keyframe
// below.
export const GESTURES = {
	wave: { hand: "👋", motion: "wave" }, // "Click me!" and the first greeting
	thumbs_up: { hand: "👍", motion: "bounce" }, // report saved
	thumbs_down: { hand: "👎", motion: "sink" },
	fingers_crossed: { hand: "🤞", motion: "sway" }, // sending
	wait: { hand: "✋", motion: "still" }, // "One moment…"
	point_up: { hand: "☝️", motion: "up" }, // at the bubble: an unsent or failed report
	point: { hand: "👉", motion: "point" }, // at Phriend: "Report it?"
	thanks: { hand: "🙏", motion: "bow" },
	praise: { hand: "🙌", motion: "raise" },
	high_five: { hand: "🖐️", motion: "slap" },
	clap: { hand: "👏", motion: "clap" },
	heart: { hand: "❤️", motion: "beat" },
	star: { hand: "⭐", motion: "twinkle" },
	alert: { hand: "‼️", motion: "pulse" }, // the red double exclamation
};

const REACT_MS = 1600; // how long a reaction without words shows
const LONG_PRESS_MS = 550; // touch: a press this long opens the menu (#2010)

// Colours and type for everything inside the Shadow DOM (the flow adds its own rules).
const BASE_CSS = `
:host {
	all: initial;
	--ph-bg: #ffffff; --ph-surface: #f7f7f8; --ph-text: #171717; --ph-muted: #6b6b6b;
	--ph-border: rgba(0, 0, 0, 0.12); --ph-border-strong: rgba(0, 0, 0, 0.22);
	--ph-accent: #171717; --ph-on-accent: #ffffff; --ph-focus: #2f6fdb;
	--ph-chip: #eef3fd; --ph-chip-text: #1d4ea3; --ph-chip-border: #a9c2f0;
	--ph-danger: #c62f2f; --ph-on-danger: #ffffff; --ph-success: #23824a; --ph-red: #e5222b;
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
	--ph-danger: #f08a8a; --ph-on-danger: #1f1f1f; --ph-success: #7ccf9b;
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
/* Dark mode: Phriend stays black and glows, so it stands out on a black page (#1934). */
:host([data-theme="dark"]) .ball svg {
	filter: drop-shadow(0 0 4px rgba(255, 255, 255, 0.55)) drop-shadow(0 0 12px rgba(255, 255, 255, 0.25));
}
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
/* Leave me in peace (#2010): eyes closed, slow breathing, a "z" rising now and then. */
.ball.dozing .eyes { animation: none; transform: scaleY(0.12); }
.ball.dozing .body { animation-duration: 32s; }
.zzz { position: absolute; right: 4px; top: -6px; display: none; pointer-events: none;
	font-size: 13px; font-weight: 600; font-style: italic; color: var(--ph-muted); }
.ball.dozing .zzz { display: block; animation: zzz 3.5s ease-out infinite; }
@keyframes zzz { 0% { opacity: 0; transform: translate(0, 6px) scale(0.7); } 30% { opacity: 1; }
	100% { opacity: 0; transform: translate(8px, -12px) scale(1.15); } }
:host([data-paused]) * { animation-play-state: paused !important; }
/* "hidden" always hides, whatever display a class sets (AI review of !1162) */
[hidden] { display: none !important; }
@media (prefers-reduced-motion: reduce) {
	.body, .shadow, .eyes, .ball:hover .leg-l, .ball:hover .leg-r, .ball.busy .eyes { animation: none; }
	.ball.hop .body { animation: none; }
	.hand.show { animation: none !important; }
	.ball.dozing .zzz { animation: none; }
}
/* The phriend's menu (#2010): right-click, long press or the context-menu key. Where the
   bubble would be; the bubble steps aside while it is open. */
.menu {
	position: absolute; bottom: calc(100% + 8px); right: 0; min-width: 220px; max-width: 280px; padding: 6px;
	border-radius: 12px; background: var(--ph-bg); color: var(--ph-text); border: 1px solid var(--ph-border);
	box-shadow: var(--ph-shadow); font-size: 13px; line-height: 1.35; cursor: auto;
}
.ball.flip .menu { right: auto; left: 0; }
.menu.below { bottom: auto; top: calc(100% + 8px); }
.menu.scroll { overflow-y: auto; }
.menu-heading { padding: 6px 8px 2px; font-size: 11px; font-weight: 600; letter-spacing: 0.02em; color: var(--ph-muted); }
.menu-note { padding: 2px 8px 6px; font-size: 12px; color: var(--ph-muted); }
.menu-sep { height: 1px; margin: 4px 2px; background: var(--ph-border); }
.menu-row { display: flex; gap: 4px; padding: 2px 4px 4px; }
.menu button { display: block; width: 100%; padding: 6px 8px; border: 0; border-radius: 8px; background: transparent;
	color: inherit; font: inherit; text-align: left; cursor: pointer; }
.menu-row button { flex: 1; padding: 5px 4px; text-align: center; border: 1px solid var(--ph-border); }
.menu button:hover, .menu button:focus-visible { background: var(--ph-surface); outline: none; }
.menu button:focus-visible { box-shadow: 0 0 0 2px var(--ph-focus); }
/* The hand beside the ball, at the side away from the badge (top right). Near the left edge
   (flip) it moves to the right side, mirrored, so it stays on screen and still faces Phriend. */
.hand {
	position: absolute; left: -16px; top: 20px; font-size: 22px; line-height: 1; pointer-events: none;
	font-family: "Apple Color Emoji", "Segoe UI Emoji", "Noto Color Emoji", sans-serif;
	opacity: 0; transform: scale(0.4); transform-origin: 70% 90%; transition: opacity 0.2s, transform 0.2s;
}
.hand.show { opacity: 1; transform: none; }
.ball.flip .hand { left: auto; right: -10px; scale: -1 1; }
.hand.show[data-motion="wave"] { animation: hand-wave 0.5s ease-in-out infinite alternate; }
.hand.show[data-motion="bounce"] { animation: hand-bounce 0.6s ease-out 1; }
.hand.show[data-motion="sway"] { animation: hand-sway 1.2s ease-in-out infinite alternate; }
.hand.show[data-motion="up"] { animation: hand-up 1s ease-in-out infinite; }
.hand.show[data-motion="point"] { animation: hand-point 1s ease-in-out infinite; }
.hand.show[data-motion="sink"] { animation: hand-sink 0.6s ease-out 1; }
.hand.show[data-motion="slap"] { animation: hand-slap 0.5s ease-out 1; }
.hand.show[data-motion="bow"] { animation: hand-bow 0.8s ease-in-out 2; }
.hand.show[data-motion="raise"] { animation: hand-raise 0.4s ease-in-out infinite alternate; }
.hand.show[data-motion="clap"] { animation: hand-clap 0.3s ease-in-out infinite alternate; }
.hand.show[data-motion="beat"] { animation: hand-beat 0.8s ease-in-out infinite; }
.hand.show[data-motion="twinkle"] { animation: hand-twinkle 1.2s ease-in-out infinite; }
.hand.show[data-motion="pulse"] { animation: hand-pulse 0.7s ease-in-out infinite; }
@keyframes hand-wave { from { transform: rotate(-14deg); } to { transform: rotate(22deg); } }
@keyframes hand-bounce { 0% { transform: scale(0.4); } 55% { transform: translateY(-5px) scale(1.25); } 100% { transform: none; } }
@keyframes hand-sink { 0% { transform: scale(0.4); } 55% { transform: translateY(4px) scale(1.15); } 100% { transform: none; } }
@keyframes hand-sway { from { transform: rotate(-7deg); } to { transform: rotate(7deg); } }
@keyframes hand-up { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-5px); } }
@keyframes hand-point { 0%, 100% { transform: translateX(0); } 50% { transform: translateX(4px); } }
@keyframes hand-slap { 0% { transform: translateX(-6px) rotate(-20deg) scale(0.6); } 60% { transform: translateX(3px) rotate(6deg) scale(1.2); } 100% { transform: none; } }
@keyframes hand-bow { 0%, 100% { transform: none; } 40% { transform: translateY(3px) rotate(10deg); } }
@keyframes hand-raise { from { transform: translateY(0); } to { transform: translateY(-4px); } }
@keyframes hand-clap { from { transform: scale(1); } to { transform: scale(0.85) rotate(-6deg); } }
@keyframes hand-beat { 0%, 100% { transform: scale(1); } 20% { transform: scale(1.22); } 40% { transform: scale(0.95); } 60% { transform: scale(1.12); } }
@keyframes hand-twinkle { 0%, 100% { transform: rotate(0) scale(1); } 50% { transform: rotate(18deg) scale(1.15); } }
@keyframes hand-pulse { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.25); } }
.badge {
	position: absolute; top: -2px; right: -2px; border: 0; font-family: inherit; min-width: 20px; height: 20px; padding: 0 5px;
	border-radius: 10px; background: #e03636; color: #fff; font-size: 11px; font-weight: 600;
	line-height: 20px; text-align: center; cursor: pointer; box-shadow: 0 0 0 2px var(--ph-bg);
}
.badge:empty { display: none; }
/* The shortcut, small and light under the feet: an invitation to try it (PM, 2026-11-15). */
.keys { position: absolute; top: calc(100% + 1px); left: 50%; transform: translateX(-50%);
	padding: 1px 6px; border-radius: 6px; white-space: nowrap; pointer-events: none;
	font-size: 11px; line-height: 15px; letter-spacing: 0.02em; color: var(--ph-muted); opacity: 0.75;
	background: color-mix(in srgb, var(--ph-bg) 70%, transparent); }
.keys:empty { display: none; }
.ball:hover .keys { opacity: 1; }
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
.bubble.sticky { padding-right: 28px; }
.bubble-close { position: absolute; top: 4px; right: 4px; width: 20px; height: 20px; padding: 0; border: 0; border-radius: 6px;
	background: transparent; color: var(--ph-muted); font: inherit; font-size: 15px; line-height: 20px; cursor: pointer; }
.bubble-close:hover { color: var(--ph-text); background: var(--ph-surface); }
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
	// options: { label, on_click, on_badge_click, on_first_interest, start, hands, menu }
	// hands: false when "Hands and reactions" is off in Phriend Settings (#2009)
	// menu: optional () => entries for the menu (#2010), see open_menu(); none = no menu
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
				<div class="menu" role="menu" hidden></div>
				<div class="hit" role="button" tabindex="0" aria-label="${escape_html(options.label)}" title="${escape_html(options.label)}">${SVG}</div>
				<span class="hand" aria-hidden="true"></span>
				<span class="zzz" aria-hidden="true">z</span>
				<span class="pending"></span>
				<span class="keys" aria-hidden="true"></span>
				<button type="button" class="badge"></button>
			</div>
			<div class="layer"></div>`;
		document.body.appendChild(this.host);

		this.root = this.shadow.querySelector(".ball");
		this.hit = this.shadow.querySelector(".hit"); // the ball itself: drag, click, keyboard
		this.bubble = this.shadow.querySelector(".bubble");
		this.menu = this.shadow.querySelector(".menu");
		this.hand = this.shadow.querySelector(".hand");
		this.badge = this.shadow.querySelector(".badge");
		this.keys = this.shadow.querySelector(".keys");
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
		this.setup_menu();

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
		watch_theme(apply);
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
		// room for the keys label under the feet, measured: it follows the CSS
		const keys = this.keys && this.keys.textContent ? this.keys.offsetHeight + 1 : 0;
		const h = (this.root.offsetHeight || 76) + keys;
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
		let pressed = false; // a long press opened the menu: no click when the finger lifts
		let press_timer = null;

		this.hit.addEventListener("pointerdown", (e) => {
			if (e.button !== 0) return;
			const rect = this.root.getBoundingClientRect();
			start = { x: e.clientX, y: e.clientY, dx: e.clientX - rect.left, dy: e.clientY - rect.top };
			dragging = false;
			pressed = false;
			this.hit.setPointerCapture(e.pointerId);
			// touch and pen have no right click: a long press opens the menu (#2010)
			clearTimeout(press_timer);
			if (e.pointerType !== "mouse" && this.options.menu) {
				press_timer = setTimeout(() => {
					if (!start || dragging) return;
					pressed = true;
					this.open_menu();
				}, LONG_PRESS_MS);
			}
		});

		this.hit.addEventListener("pointermove", (e) => {
			if (!start) return;
			if (!dragging && !pressed && Math.hypot(e.clientX - start.x, e.clientY - start.y) > 5) {
				dragging = true;
				clearTimeout(press_timer);
				this.root.classList.add("dragging");
			}
			if (dragging) this.set_position(e.clientX - start.dx, e.clientY - start.dy);
		});

		const end = (e, cancelled) => {
			clearTimeout(press_timer);
			if (!start) return;
			this.hit.releasePointerCapture(e.pointerId);
			start = null;
			if (pressed) {
				pressed = false;
			} else if (dragging) {
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
		// no eyes following the pointer for people who asked for less motion
		if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
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

	// Leave me in peace (#2010): eyes closed, slow breathing, a rising "z".
	set_dozing(dozing) {
		this.root.classList.toggle("dozing", !!dozing);
	}

	// ---- the menu (#2010)

	setup_menu() {
		if (!this.options.menu) return;
		this.hit.addEventListener("contextmenu", (e) => {
			e.preventDefault();
			this.open_menu();
		});
		this.hit.addEventListener("keydown", (e) => {
			if (e.key === "ContextMenu" || (e.key === "F10" && e.shiftKey)) {
				e.preventDefault();
				this.open_menu();
			}
		});
		this.menu.addEventListener("pointerdown", (e) => e.stopPropagation());
		this.menu.addEventListener("keydown", (e) => this.on_menu_key(e));
		// a click anywhere else closes it; inside the shadow root the path tells where it was
		document.addEventListener(
			"pointerdown",
			(e) => this.menu_open() && !e.composedPath().includes(this.root) && this.close_menu(false),
			true
		);
	}

	menu_open() {
		return !this.menu.hidden;
	}

	// entries from options.menu(): { heading }, { note }, { separator: true },
	// { label, action }, or { row: [{ label, action, title }] } for buttons side by side.
	// Labels and notes are plain text.
	open_menu() {
		const entries = (this.options.menu && this.options.menu()) || [];
		if (!entries.length) return;
		this.hide_bubble();
		this.menu.replaceChildren(...entries.map((entry) => this.menu_entry(entry)));
		this.menu.hidden = false;
		this.fit_menu();
		const first = this.menu.querySelector("button");
		if (first) first.focus();
	}

	menu_entry(entry) {
		const div = (cls, text) => {
			const el = document.createElement("div");
			el.className = cls;
			if (text) el.textContent = text;
			return el;
		};
		const button = (item) => {
			const b = document.createElement("button");
			b.type = "button";
			b.setAttribute("role", "menuitem");
			b.textContent = item.label;
			if (item.title) b.title = item.title;
			b.addEventListener("click", () => {
				this.close_menu(false);
				item.action();
			});
			return b;
		};
		if (entry.separator) return div("menu-sep");
		if (entry.heading) return div("menu-heading", entry.heading);
		if (entry.note) return div("menu-note", entry.note);
		if (entry.row) {
			const row = div("menu-row");
			row.setAttribute("role", "group");
			row.append(...entry.row.map(button));
			return row;
		}
		return button(entry);
	}

	// Above the ball if it fits, else below when there is more room there; scroll if neither fits.
	fit_menu() {
		const GAP = 8 + 4; // the gap to the ball and a margin to the window edge
		this.menu.classList.remove("below", "scroll");
		this.menu.style.maxHeight = "";
		const ball = this.root.getBoundingClientRect();
		const height = this.menu.offsetHeight;
		const above = ball.top - GAP;
		const below = window.innerHeight - ball.bottom - GAP;
		if (height <= above) return;
		const room = Math.max(above, below);
		this.menu.classList.toggle("below", below > above);
		if (height > room) {
			this.menu.classList.add("scroll");
			this.menu.style.maxHeight = `${Math.max(room, 120)}px`;
		}
	}

	close_menu(focus_ball = true) {
		if (!this.menu_open()) return;
		this.menu.hidden = true;
		this.menu.replaceChildren();
		if (focus_ball) this.hit.focus();
	}

	on_menu_key(e) {
		if (e.key === "Escape" || e.key === "Tab") {
			e.preventDefault();
			this.close_menu(true);
			return;
		}
		if (e.key !== "ArrowDown" && e.key !== "ArrowUp" && e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
		e.preventDefault();
		const buttons = [...this.menu.querySelectorAll("button")];
		const i = buttons.indexOf(this.shadow.activeElement);
		const step = e.key === "ArrowDown" || e.key === "ArrowRight" ? 1 : -1;
		buttons[(i + step + buttons.length) % buttons.length].focus();
	}

	// html: trusted markup built by Phriend itself (user text is escaped by the caller).
	// ms = 0 keeps the bubble until the next say() or hide_bubble().
	// gesture: a key of GESTURES; the hand shows while this bubble shows.
	say(html, ms = 4000, gesture = null) {
		this.close_menu(false); // the bubble sits where the menu is
		clearTimeout(this._bubble_timer);
		clearTimeout(this._react_timer);
		this.bubble.innerHTML = html;
		this.bubble.classList.add("show");
		this._bubble_gesture = gesture;
		this.set_hand(gesture);
		// a bubble that stays (failures, "One moment…") can be closed
		this.bubble.classList.toggle("sticky", !ms);
		if (ms) {
			this._bubble_timer = setTimeout(() => this.hide_bubble(), ms);
		} else {
			const close = document.createElement("button");
			close.type = "button";
			close.className = "bubble-close";
			close.textContent = "×";
			close.setAttribute("aria-label", this.options.close_label || "Close");
			close.addEventListener("click", () => this.hide_bubble());
			this.bubble.appendChild(close);
		}
		return this.bubble;
	}

	hide_bubble() {
		clearTimeout(this._bubble_timer);
		clearTimeout(this._react_timer);
		this.bubble.classList.remove("show");
		this._bubble_gesture = null;
		this.set_hand(null);
	}

	bubble_showing() {
		return this.bubble.classList.contains("show");
	}

	// A reaction without words (#2009): the emoji shows for a moment beside the ball. Over a
	// bubble it borrows the bubble's place and gives the bubble's hand back afterwards.
	react(name, ms = REACT_MS) {
		if (!GESTURES[name] || this.options.hands === false) return false;
		clearTimeout(this._react_timer);
		this.set_hand(name);
		if (name === "praise" || name === "high_five") this.hop();
		this._react_timer = setTimeout(
			() => this.set_hand(this.bubble_showing() ? this._bubble_gesture : null),
			ms
		);
		return true;
	}

	set_hand(gesture) {
		// no hands at all when "Hands and reactions" is off (Phriend Settings → Features)
		const g = this.options.hands !== false && gesture && GESTURES[gesture];
		this.hand.classList.remove("show");
		if (!g) return; // keep the emoji while it fades out
		this.hand.textContent = g.hand;
		this.hand.dataset.motion = g.motion;
		void this.hand.offsetWidth; // restart the motion when the same hand comes again
		this.hand.classList.add("show");
	}

	// "⌘P" under the ball; "" hides it (shortcut switched off)
	set_keys(keys) {
		this.keys.textContent = keys || "";
		this.clamp_into_view(); // the label below may need room at the bottom edge
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
