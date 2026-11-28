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
export const SPEED_WINDOW_MS = 30; // speed is measured over at least this long, not between two events

// A move from `moves`, never the same as the last one. random: () => [0, 1), for the tests.
export function pick(moves, previous, random = Math.random) {
	const choices = moves.length > 1 ? moves.filter((m) => m !== previous) : moves;
	return choices[Math.min(choices.length - 1, Math.floor(random() * choices.length))];
}

// last: when this trigger last played (ms), or undefined
export function cooled_down(last, now, cooldown = COOLDOWN_MS) {
	return !last || now - last >= cooldown;
}

// The fastest stretch of a drag: samples [{x, y, t}] in order. The path travelled over at least
// SPEED_WINDOW_MS, so two events a millisecond apart (fast mice, touch, rounded time stamps) can't
// make a calm drag look like a shake (AI review of !1285); a shake back and forth still counts.
export function top_speed(samples, window_ms = SPEED_WINDOW_MS) {
	let top = 0;
	for (let i = 1; i < samples.length; i++) {
		let path = 0;
		let j = i;
		while (j > 0 && samples[i].t - samples[j].t < window_ms) {
			path += Math.hypot(samples[j].x - samples[j - 1].x, samples[j].y - samples[j - 1].y);
			j--;
		}
		const dt = samples[i].t - samples[j].t;
		if (dt < window_ms) continue; // not long enough yet
		top = Math.max(top, path / dt);
	}
	return top;
}
