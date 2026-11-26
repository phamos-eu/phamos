// The ball itself: a black ball with legs, drawn once into a Shadow DOM so Bootstrap (Desk)
// and Tailwind (cockpits) can't change how it looks. This module is loaded on every page,
// so it stays small: the capture and the report flow load on demand (flow.js).

import { bubble_path, jitter, TAIL_H, TAIL_INSET, TAIL_LEAN } from "./bubble";
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
			<g class="eye eye-l">
				<ellipse cx="24" cy="30" rx="5.5" ry="6.5" fill="#fff"/>
				<circle class="pupil" cx="24" cy="31" r="2.8" fill="#111"/>
			</g>
			<g class="eye eye-r">
				<ellipse cx="40" cy="30" rx="5.5" ry="6.5" fill="#fff"/>
				<circle class="pupil" cx="40" cy="31" r="2.8" fill="#111"/>
			</g>
		</g>
		<path class="mouth" d="M27 42 Q32 46.5 37 42" stroke="#fff" stroke-width="1.8" fill="none" stroke-linecap="round" opacity="0.85"/>
	</g>
</svg>`;

// The emoji that goes with a bubble (#1990), say(html, ms, "<gesture>"), and the reactions
// without words, react("<gesture>") (#2009). The system's own emoji, default skin tone (PM,
// 2026-11-21), shown inside the speech bubble, in front of its text (PM, 2026-11-21). The motion
// names a keyframe below.
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
	muscle: { hand: "💪", motion: "flex" }, // "ready", back from quiet (#2010)
	rocket: { hand: "🚀", motion: "launch" }, // "let's go", back from quiet (#2010)
	music: { hand: "🎵", motion: "sway" }, // dancing (#2013)
	dizzy: { hand: "💫", motion: "twinkle" }, // shaken around (#2013)
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
.hit svg { width: 100%; height: 100%; overflow: visible; display: block; filter: drop-shadow(0 4px 6px rgba(0, 0, 0, 0.25)); }
/* Dark mode: Phriend stays black and glows, so it stands out on a black page (#1934). */
:host([data-theme="dark"]) .hit svg {
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
/* Easter eggs (#2013): one move at a time, class "play-<move>" for its length (play.js). */
.eye { transform-box: fill-box; transform-origin: center; }
.ball.play-spin .body { transform-origin: 50% 39%; animation: ph-spin 0.9s ease-in-out 1; }
.ball.play-double_hop .body { animation: ph-double-hop 0.95s ease-out 1; }
.ball.play-double_hop .leg-l { animation: wiggle-l 0.24s ease-in-out 4 alternate; }
.ball.play-double_hop .leg-r { animation: wiggle-r 0.24s ease-in-out 4 alternate; }
.ball.play-wink .eyes { animation: none; }
.ball.play-wink .eye-r { animation: ph-wink 0.7s ease-in-out 1; }
.ball.play-peekaboo .eyes { animation: ph-peekaboo 1.1s ease-in-out 1; }
.ball.play-look_around .eyes { animation: ph-look 1.7s ease-in-out 1; }
.ball.play-dance .body { animation: ph-dance 0.5s ease-in-out 4 alternate; }
.ball.play-dance .leg-l { animation: wiggle-l 0.25s ease-in-out 8 alternate; }
.ball.play-dance .leg-r { animation: wiggle-r 0.25s ease-in-out 8 alternate; }
.ball.play-dizzy .body { animation: ph-wobble 0.3s ease-in-out 5 alternate; }
.ball.play-dizzy .eyes { animation: none; }
.ball.play-dizzy .eye { animation: ph-dizzy-eye 0.5s linear 3; }
@keyframes ph-spin { from { transform: rotate(0); } to { transform: rotate(360deg); } }
@keyframes ph-double-hop { 0%, 50%, 100% { transform: translateY(0); } 20% { transform: translateY(-12px); }
	70% { transform: translateY(-9px); } 40%, 90% { transform: translateY(0) scale(1.04, 0.96); } }
@keyframes ph-wink { 0%, 100% { transform: scaleY(1); } 30%, 65% { transform: scaleY(0.1); } }
@keyframes ph-peekaboo { 0% { transform: scale(1); } 15%, 50% { transform: scaleY(0.08); } 65% { transform: scale(1.22); } 100% { transform: scale(1); } }
@keyframes ph-look { 0%, 100% { transform: translateX(0); } 20%, 35% { transform: translateX(-3.5px); } 55%, 75% { transform: translateX(3.5px); } }
@keyframes ph-dance { from { transform: rotate(-7deg) translateY(0); } to { transform: rotate(7deg) translateY(-3px); } }
@keyframes ph-wobble { from { transform: rotate(-9deg); } to { transform: rotate(9deg); } }
@keyframes ph-dizzy-eye { from { transform: rotate(0); } to { transform: rotate(360deg); } }
/* Leave me in peace (#2010): Phriend steps back but stays there, ready. Never asleep ("sleeping
   on the job" is not the message, PM 2026-11-21): smaller, a little faded, without face and
   legs; still breathing. Full strength again while the pointer is on it. */
.hit svg { transition: transform 0.4s ease, opacity 0.4s ease; transform-origin: 50% 60%; }
.eyes, .mouth, .leg { transition: opacity 0.3s ease; }
.ball.resting .hit svg { transform: translateY(10px) scale(0.6); opacity: 0.55; }
.ball.resting .eyes, .ball.resting .mouth, .ball.resting .leg { opacity: 0; }
.ball.resting .shadow { opacity: 0; animation: none; }
.ball.resting:hover .hit svg, .ball.resting .hit:focus-visible svg { opacity: 0.9; }
:host([data-paused]) * { animation-play-state: paused !important; }
/* "hidden" always hides, whatever display a class sets (AI review of !1162) */
[hidden] { display: none !important; }
@media (prefers-reduced-motion: reduce) {
	.body, .shadow, .eyes, .ball:hover .leg-l, .ball:hover .leg-r, .ball.busy .eyes { animation: none; }
	.ball.hop .body { animation: none; }
	.ball[class*="play-"] .body, .ball[class*="play-"] .eyes, .ball[class*="play-"] .eye, .ball[class*="play-"] .leg { animation: none !important; }
	.emoji { animation: none !important; }
	.hit svg, .eyes, .mouth, .leg { transition: none; }
}
/* The phriend's menu (#2010): right-click, long press or the context-menu key. Where the
   bubble would be; the bubble steps aside while it is open. */
.menu {
	position: absolute; z-index: 3; bottom: calc(100% + 8px); right: 0; min-width: 220px; max-width: 280px; padding: 6px;
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
/* The emoji inside the bubble, in front of the text (PM, 2026-11-21). */
.emoji { display: inline-block; margin-right: 6px; font-size: 18px; line-height: 1; vertical-align: -3px;
	font-family: "Apple Color Emoji", "Segoe UI Emoji", "Noto Color Emoji", sans-serif; transform-origin: 50% 80%; }
.bubble.only { padding: 6px 10px; }
.bubble.only .emoji { margin: 0; font-size: 26px; vertical-align: middle; }
.emoji[data-motion="wave"] { animation: hand-wave 0.5s ease-in-out infinite alternate; }
.emoji[data-motion="bounce"] { animation: hand-bounce 0.6s ease-out 1; }
.emoji[data-motion="sway"] { animation: hand-sway 1.2s ease-in-out infinite alternate; }
.emoji[data-motion="up"] { animation: hand-up 1s ease-in-out infinite; }
.emoji[data-motion="point"] { animation: hand-point 1s ease-in-out infinite; }
.emoji[data-motion="sink"] { animation: hand-sink 0.6s ease-out 1; }
.emoji[data-motion="slap"] { animation: hand-slap 0.5s ease-out 1; }
.emoji[data-motion="bow"] { animation: hand-bow 0.8s ease-in-out 2; }
.emoji[data-motion="raise"] { animation: hand-raise 0.4s ease-in-out infinite alternate; }
.emoji[data-motion="clap"] { animation: hand-clap 0.3s ease-in-out infinite alternate; }
.emoji[data-motion="beat"] { animation: hand-beat 0.8s ease-in-out infinite; }
.emoji[data-motion="twinkle"] { animation: hand-twinkle 1.2s ease-in-out infinite; }
.emoji[data-motion="pulse"] { animation: hand-pulse 0.7s ease-in-out infinite; }
.emoji[data-motion="flex"] { animation: hand-flex 0.5s ease-in-out 3 alternate; }
.emoji[data-motion="launch"] { animation: hand-launch 1.4s ease-in 1 forwards; }
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
@keyframes hand-flex { from { transform: rotate(0) scale(1); } to { transform: rotate(-12deg) scale(1.2); } }
@keyframes hand-launch { 0% { transform: none; } 30% { transform: translate(-2px, 2px); } 100% { transform: translate(14px, -26px); opacity: 0; } }
.badge, .badge-testing {
	position: absolute; top: -2px; right: -2px; border: 0; font-family: inherit; min-width: 20px; height: 20px; padding: 0 5px;
	border-radius: 10px; background: #e03636; color: #fff; font-size: 11px; font-weight: 600;
	line-height: 20px; text-align: center; cursor: pointer; box-shadow: 0 0 0 2px var(--ph-bg);
}
.badge:empty, .badge-testing:empty { display: none; }
/* Tickets from this page Testing on Production, under the red badge; GitLab's label colour.
   Its own class, not .badge, so the red badge's lookup can never pick it up (AI review of !1322). */
.badge-testing { top: 20px; background: #5b2a86; }
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
/* One voice (#2011): something waits for the user. Click: the oldest one, in a bubble. */
.waiting { position: absolute; left: 30px; top: -5px; min-width: 14px; height: 14px; padding: 0 3px; border: 0;
	border-radius: 7px; background: #2f6fdb; color: #fff; font: 600 9px/14px var(--ph-font); text-align: center;
	cursor: pointer; box-shadow: 0 0 0 2px var(--ph-bg); }
.waiting:focus-visible { outline: 2px solid var(--ph-focus); outline-offset: 2px; }
.ball.resting .waiting { opacity: 0.7; }
/* The bubble: its outline (box and tail as one shape) is an SVG path drawn to its size
   (bubble.js), so border and shadow run round the tail too. Each one lands a little off (--jx,
   --jy, --jr: the jitter), tilting round its tail. Half up, half to the side (PM, 2026-11-21):
   the tail's tip just over Phriend's scalp, above the eyes, leaning in; always in front of
   Phriend, never behind it. The tilt is only on the way in: a shown bubble always rests
   horizontal, so it is easy to read (PM, 2026-11-23, #2095). */
.bubble {
	position: absolute; z-index: 3; bottom: 76px; right: 36px; width: max-content; max-width: 260px;
	padding: 8px 12px; color: var(--ph-text); font-size: 13px; line-height: 1.4;
	--jx: 0px; --jy: 0px; --jr: 0deg; transform-origin: calc(100% - 22px) calc(100% + 8px);
	opacity: 0; transform: translate(var(--jx), calc(var(--jy) + 6px)) rotate(var(--jr));
	transition: opacity 0.2s, transform 0.2s; pointer-events: none; cursor: auto;
}
.bubble.show { opacity: 1; transform: translate(var(--jx), var(--jy)) rotate(0deg); pointer-events: auto; }
.bubble .shape { position: absolute; left: 0; top: 0; overflow: visible; pointer-events: none;
	filter: drop-shadow(0 6px 14px rgba(0, 0, 0, 0.15)) drop-shadow(0 1px 3px rgba(0, 0, 0, 0.08)); }
:host([data-theme="dark"]) .bubble .shape { filter: drop-shadow(0 6px 16px rgba(0, 0, 0, 0.55)); }
.bubble .shape path { fill: var(--ph-bg); stroke: var(--ph-border-strong); stroke-width: 1; }
.bubble .content { position: relative; }
/* Rating a fix (#2014): thumbs or stars, then an optional comment, inside the bubble. */
.rate-q { margin-bottom: 6px; }
.rate-row { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.rate-row button.pick { min-width: 36px; height: 32px; padding: 0 8px; border: 1px solid var(--ph-border-strong); border-radius: 8px;
	background: var(--ph-surface); color: var(--ph-text); font-size: 18px; line-height: 1; cursor: pointer;
	font-family: "Apple Color Emoji", "Segoe UI Emoji", "Noto Color Emoji", var(--ph-font); }
.rate-row button.pick:hover, .rate-row button.pick:focus-visible { border-color: var(--ph-focus); outline: none; }
.rate-row.stars button.pick { min-width: 0; width: 30px; padding: 0; font-size: 17px; color: #e0a800; }
.rate-row.stars button.pick.on { background: #fff6d6; }
:host([data-theme="dark"]) .rate-row.stars button.pick.on { background: #3a3215; }
.rate-foot { margin-top: 6px; font-size: 12px; color: var(--ph-muted); }
.rate-comment { display: block; width: 100%; min-width: 220px; margin: 6px 0; padding: 6px 8px; resize: vertical;
	border: 1px solid var(--ph-border-strong); border-radius: 8px; background: var(--ph-bg); color: var(--ph-text);
	font: inherit; font-size: 13px; }
.rate-comment:focus { outline: 2px solid var(--ph-focus); outline-offset: 0; }
.rate-send { padding: 4px 12px; border: 0; border-radius: 8px; background: var(--ph-accent); color: var(--ph-on-accent);
	font: inherit; font-size: 13px; cursor: pointer; }
.bubble.sticky { padding-right: 28px; }
.bubble-close { position: absolute; top: 4px; right: 4px; width: 20px; height: 20px; padding: 0; border: 0; border-radius: 6px;
	background: transparent; color: var(--ph-muted); font: inherit; font-size: 15px; line-height: 20px; cursor: pointer; }
.bubble-close:hover { color: var(--ph-text); background: var(--ph-surface); }
.ball.flip .bubble { right: auto; left: 36px; transform-origin: 22px calc(100% + 8px); }
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
	// on_waiting_click, waiting_label(count): the blue dot of things waiting (#2011)
	// on_drag_end(samples): a drag ended, with its last moves [{x, y, t}] (#2013)
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
				<div class="bubble" role="status" aria-live="polite"><svg class="shape" aria-hidden="true"><path/></svg><div class="content"></div></div>
				<div class="menu" role="menu" hidden></div>
				<div class="hit" role="button" tabindex="0" aria-label="${escape_html(options.label)}" title="${escape_html(options.label)}">${SVG}</div>
				<span class="pending"></span>
				<button type="button" class="waiting" hidden></button>
				<span class="keys" aria-hidden="true"></span>
				<button type="button" class="badge"></button>
				<button type="button" class="badge-testing"></button>
			</div>
			<div class="layer"></div>`;
		document.body.appendChild(this.host);

		this.root = this.shadow.querySelector(".ball");
		this.hit = this.shadow.querySelector(".hit"); // the ball itself: drag, click, keyboard
		this.bubble = this.shadow.querySelector(".bubble");
		this.menu = this.shadow.querySelector(".menu");
		this.bubble_content = this.bubble.querySelector(".content");
		this.bubble_shape = this.bubble.querySelector(".shape");
		// The outline follows the bubble's size (#2095): a bubble that came up while Phriend was
		// hidden (pinned off screen on Ophice) measured 0 × 0 and stayed without its background.
		if (typeof ResizeObserver !== "undefined") {
			this._bubble_size = "";
			new ResizeObserver(() => {
				const size = `${this.bubble.offsetWidth}x${this.bubble.offsetHeight}`;
				if (size === this._bubble_size) return;
				this._bubble_size = size;
				if (this.bubble_showing()) this.draw_bubble(false);
			}).observe(this.bubble);
		}
		this.badge = this.shadow.querySelector(".badge");
		this.waiting = this.shadow.querySelector(".waiting");
		this.keys = this.shadow.querySelector(".keys");
		this.testing_badge = this.shadow.querySelector(".badge-testing");
		this.layer = this.shadow.querySelector(".layer"); // the report flow mounts here
		this.pupils = this.shadow.querySelectorAll(".pupil");

		this.sync_theme();
		if (options.start) {
			this.root.style.right = `${options.start.right}px`;
			this.root.style.bottom = `${options.start.bottom}px`;
		}
		// Pinned (Ophice's map, #2053): the host places the ball; it is not dragged and does not
		// remember a position (that one belongs to the floating ball of Desk and the cockpits).
		if (!options.pinned) this.restore_position();
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
		this.testing_badge.addEventListener("pointerdown", (e) => e.stopPropagation());
		this.testing_badge.addEventListener("click", (e) => {
			e.stopPropagation();
			options.on_testing_badge_click && options.on_testing_badge_click();
		});
		this.bubble.addEventListener("pointerdown", (e) => e.stopPropagation());
		this.waiting.addEventListener("pointerdown", (e) => e.stopPropagation());
		this.waiting.addEventListener("click", (e) => {
			e.stopPropagation();
			options.on_waiting_click && options.on_waiting_click();
		});
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

	/**
	 * Pinned mode: stand on a spot of the host's page, `size` px wide (the height follows the
	 * ball's 64:76 shape), or hide while the spot is not on screen.
	 * @param {{left: number, top: number, size: number} | null} spot
	 */
	pin(spot) {
		this.host.style.display = spot ? "" : "none";
		if (!spot) return;
		const width = Math.round(spot.size);
		Object.assign(this.root.style, {
			width: `${width}px`,
			height: `${Math.round((width * 76) / 64)}px`,
			left: `${Math.round(spot.left)}px`,
			top: `${Math.round(spot.top)}px`,
			right: "auto",
			bottom: "auto",
		});
		const flip = spot.left < 260; // keep the speech bubble on screen
		if (flip !== this.root.classList.contains("flip")) {
			this.root.classList.toggle("flip", flip);
			if (this.bubble_showing()) this.draw_bubble(false); // the tail moves to the other side
		}
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
		let samples = []; // the drag's last moves, to tell a fast shake (#2013)

		this.hit.addEventListener("pointerdown", (e) => {
			if (e.button !== 0) return;
			const rect = this.root.getBoundingClientRect();
			start = { x: e.clientX, y: e.clientY, dx: e.clientX - rect.left, dy: e.clientY - rect.top };
			dragging = false;
			pressed = false;
			samples = [];
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
			if (!dragging && !pressed && !this.options.pinned && Math.hypot(e.clientX - start.x, e.clientY - start.y) > 5) {
				dragging = true;
				clearTimeout(press_timer);
				this.root.classList.add("dragging");
			}
			if (dragging) {
				this.set_position(e.clientX - start.dx, e.clientY - start.dy);
				samples.push({ x: e.clientX, y: e.clientY, t: e.timeStamp });
				if (samples.length > 12) samples.shift();
			}
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
				if (this.options.on_drag_end) this.options.on_drag_end(samples);
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

	// An easter egg (#2013): one move of play.js MOVES for `ms`; the next one waits.
	play(name, ms) {
		if (this._playing) return false;
		this._playing = name;
		this.root.classList.add(`play-${name}`);
		setTimeout(() => {
			this.root.classList.remove(`play-${name}`);
			this._playing = null;
		}, ms);
		return true;
	}

	set_busy(busy) {
		this.root.classList.toggle("busy", !!busy);
	}

	set_away(away) {
		this.root.classList.toggle("away", !!away);
	}

	// One voice (#2011): how many things wait behind the dot; 0 hides it.
	set_waiting(count) {
		this.waiting.hidden = !count;
		this.waiting.textContent = count > 1 ? String(count) : "";
		const label = this.options.waiting_label ? this.options.waiting_label(count) : "";
		this.waiting.title = label;
		this.waiting.setAttribute("aria-label", label);
	}

	set_pending(pending) {
		this.root.classList.toggle("has-pending", !!pending);
	}

	// Leave me in peace (#2010): smaller, faded, no face and legs, but there and ready.
	set_resting(resting) {
		this.root.classList.toggle("resting", !!resting);
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
	// gesture: a key of GESTURES; its emoji shows inside the bubble, in front of the text.
	// on_close: called when the user closes a bubble that stays (ms = 0) with ×, not when it is
	// replaced or hidden by code (#2014: a rating question put off to another day)
	say(html, ms = 4000, gesture = null, { on_close = null } = {}) {
		clearTimeout(this._react_timer);
		this._bubble_gesture = gesture;
		this.show_bubble(`${this.emoji_html(gesture)}${html}`, ms, false, on_close);
		return this.bubble;
	}

	// New content in the bubble that is showing (a next step), redrawn to its size, same place.
	refill_bubble(html) {
		this.bubble_content.innerHTML = html;
		this.draw_bubble(false);
		return this.bubble;
	}

	emoji_html(gesture) {
		// no emoji when "Hands and Reactions" is off (Phriend Settings → Features)
		const g = this.options.hands !== false && gesture && GESTURES[gesture];
		return g ? `<span class="emoji" data-motion="${g.motion}" aria-hidden="true">${g.hand}</span>` : "";
	}

	show_bubble(html, ms, only_emoji, on_close = null) {
		this.close_menu(false); // the bubble sits where the menu is
		clearTimeout(this._bubble_timer);
		const old_close = this.bubble.querySelector(".bubble-close");
		if (old_close) old_close.remove();
		this.bubble_content.innerHTML = html;
		this.bubble.classList.toggle("only", !!only_emoji);
		// a bubble that stays (failures, "One moment…") can be closed
		this.bubble.classList.toggle("sticky", !ms);
		if (!ms) {
			const close = document.createElement("button");
			close.type = "button";
			close.className = "bubble-close";
			close.textContent = "×";
			close.setAttribute("aria-label", this.options.close_label || "Close");
			close.addEventListener("click", () => {
				this.hide_bubble();
				if (on_close) on_close();
			});
			this.bubble.appendChild(close);
		}
		this.draw_bubble();
		this.bubble.classList.add("show");
		if (ms) this._bubble_timer = setTimeout(() => this.hide_bubble(), ms);
	}

	// The outline to the bubble's size, landing a little off each time (again: a new place).
	draw_bubble(again = true) {
		const j = again || !this._jitter ? jitter() : this._jitter;
		this._jitter = j;
		this.bubble.style.setProperty("--jx", `${j.x}px`);
		this.bubble.style.setProperty("--jy", `${j.y}px`);
		this.bubble.style.setProperty("--jr", `${j.rot}deg`);
		const w = this.bubble.offsetWidth;
		const h = this.bubble.offsetHeight;
		const flipped = this.root.classList.contains("flip");
		const tail_x = (flipped ? TAIL_INSET : w - TAIL_INSET) + j.tail;
		this.bubble_shape.setAttribute("width", w);
		this.bubble_shape.setAttribute("height", h + TAIL_H);
		this.bubble_shape.setAttribute("viewBox", `0 0 ${w} ${h + TAIL_H}`);
		const lean = flipped ? -TAIL_LEAN : TAIL_LEAN; // the tip leans towards Phriend
		this.bubble_shape.firstElementChild.setAttribute("d", bubble_path(w, h, tail_x, { lean }));
	}

	hide_bubble() {
		clearTimeout(this._bubble_timer);
		clearTimeout(this._react_timer);
		this.bubble.classList.remove("show");
		this._bubble_gesture = null;
	}

	bubble_showing() {
		return this.bubble.classList.contains("show");
	}

	// A reaction without words (#2009): the emoji alone in a small bubble for a moment. Over a
	// bubble with words it takes the emoji's place in it and gives it back afterwards.
	react(name, ms = REACT_MS) {
		if (!GESTURES[name] || this.options.hands === false) return false;
		clearTimeout(this._react_timer);
		if (name === "praise" || name === "high_five") this.hop();
		if (this.bubble_showing() && !this.bubble.classList.contains("only")) {
			const before = this.bubble_content.querySelector(".emoji");
			this.bubble_content.insertAdjacentHTML("afterbegin", this.emoji_html(name));
			if (before) before.remove();
			const gesture = this._bubble_gesture;
			this._react_timer = setTimeout(() => {
				const now = this.bubble_content.querySelector(".emoji");
				if (now) now.remove();
				if (gesture) this.bubble_content.insertAdjacentHTML("afterbegin", this.emoji_html(gesture));
			}, ms);
			return true;
		}
		this._bubble_gesture = null;
		this.show_bubble(this.emoji_html(name), ms, true);
		return true;
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

	// color: the label's colour as GitLab has it ("#rrggbb"); empty keeps the CSS purple
	set_testing_badge(count, title, color) {
		this.testing_badge.textContent = count ? String(count) : "";
		this.testing_badge.title = title || "";
		this.testing_badge.setAttribute("aria-label", title || "");
		this.testing_badge.style.background = color || "";
	}
}
