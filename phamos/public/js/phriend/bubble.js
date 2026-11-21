// The speech bubble's outline as one SVG path (PM, 2026-11-21): the rounded box and its tail are
// one shape, so the border and the shadow run round the tail too, sharp at any zoom. And a
// little jitter, so a bubble doesn't land in exactly the same place every time.

export const RADIUS = 12;
export const TAIL_W = 14; // where the tail meets the box
export const TAIL_H = 8; // how far it reaches down to Phriend
export const TAIL_INSET = 22; // from the box's right edge (left edge when flipped)

const r1 = (n) => Math.round(n * 10) / 10;

// w, h: the box (the tail hangs below it); tail_x: where the tail's tip is, from the left.
// Drawn half a pixel in, so a 1px border lands on whole pixels.
export function bubble_path(w, h, tail_x, { r = RADIUS, tw = TAIL_W, th = TAIL_H } = {}) {
	const L = 0.5;
	const T = 0.5;
	const R = w - 0.5;
	const B = h - 0.5;
	r = Math.max(2, Math.min(r, (B - T) / 2, (R - L) / 2));
	// keep the tail clear of the rounded corners
	const x = Math.max(L + r + tw / 2, Math.min(R - r - tw / 2, tail_x));
	const right = x + tw / 2;
	const left = x - tw / 2;
	const tip_y = B + th;
	return [
		`M${r1(L + r)} ${T}`,
		`H${r1(R - r)}`,
		`A${r} ${r} 0 0 1 ${R} ${r1(T + r)}`,
		`V${r1(B - r)}`,
		`A${r} ${r} 0 0 1 ${r1(R - r)} ${B}`,
		`H${r1(right)}`,
		// a soft tail: curved in, a rounded tip, curved back
		`Q${r1(x + 1.5)} ${r1(B + th * 0.45)} ${r1(x)} ${r1(tip_y)}`,
		`Q${r1(x - 2.5)} ${r1(B + th * 0.35)} ${r1(left)} ${B}`,
		`H${r1(L + r)}`,
		`A${r} ${r} 0 0 1 ${L} ${r1(B - r)}`,
		`V${r1(T + r)}`,
		`A${r} ${r} 0 0 1 ${r1(L + r)} ${T}`,
		"Z",
	].join(" ");
}

// A little off each time: up to 6px aside, a little up or down, up to 2° of tilt, and the tail a
// few pixels along the edge. random: () => [0, 1), for the tests.
export function jitter(random = Math.random) {
	const between = (a, b) => a + (b - a) * random();
	return {
		x: r1(between(-6, 6)),
		y: r1(between(-4, 2)),
		rot: r1(between(-2, 2)),
		tail: r1(between(-6, 6)),
	};
}
