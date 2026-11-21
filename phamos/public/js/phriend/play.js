// Easter eggs (#2013): now and then Phriend plays. Pure rules here; the moves themselves are CSS
// in ball.js (class "play-<move>" on the ball), the triggers in index.js.
//
//   hover   the pointer rests on Phriend for 10 s
//   idle    no mouse or keyboard for 5 min, once per idle spell
//   drag    Phriend is dragged fast: dizzy
//
// Never a bubble with words, never counted against the daily bubble, never while quiet, while
// the report flow or the menu is open, or for people who asked for less motion. Nothing that
// looks like sleeping (PM, 2026-11-21).

// move → how long it runs (ms), and the emoji it shows alone in a small bubble, if any
export const MOVES = {
	spin: { ms: 900 },
	double_hop: { ms: 950 },
	wink: { ms: 700 },
	peekaboo: { ms: 1100 },
	look_around: { ms: 1700 },
	dance: { ms: 2000, emoji: "music" },
	dizzy: { ms: 1500, emoji: "dizzy" },
};

export const HOVER_MOVES = ["spin", "double_hop", "wink", "peekaboo", "look_around", "dance"];
export const IDLE_MOVES = ["look_around", "wink", "dance", "double_hop"];

export const HOVER_MS = 10 * 1000;
export const IDLE_MS = 5 * 60 * 1000;
export const COOLDOWN_MS = 3 * 60 * 1000; // per trigger, so it stays a surprise
export const FAST_DRAG = 1.8; // px per ms (1800 px/s) counts as shaking Phriend around

// A move from `moves`, never the same as the last one. random: () => [0, 1), for the tests.
export function pick(moves, previous, random = Math.random) {
	const choices = moves.length > 1 ? moves.filter((m) => m !== previous) : moves;
	return choices[Math.min(choices.length - 1, Math.floor(random() * choices.length))];
}

// last: when this trigger last played (ms), or undefined
export function cooled_down(last, now, cooldown = COOLDOWN_MS) {
	return !last || now - last >= cooldown;
}

// The fastest stretch of a drag: samples [{x, y, t}] in order.
export function top_speed(samples) {
	let top = 0;
	for (let i = 1; i < samples.length; i++) {
		const dt = samples[i].t - samples[i - 1].t;
		if (dt <= 0) continue;
		const d = Math.hypot(samples[i].x - samples[i - 1].x, samples[i].y - samples[i - 1].y);
		top = Math.max(top, d / dt);
	}
	return top;
}
