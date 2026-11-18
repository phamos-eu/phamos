// The drawings on the Phriend screenshot as plain data: where each one is, which one is under the
// pointer, moving one, and an undo history of actions (add, delete, replace for moves and edits).
// No DOM here, so vitest can check it (shapes.test.js); annotator.js draws them.
//
// Shapes, in screenshot pixels:
//   { type: "pen", points: [from, tip], w }       a straight arrow
//   { type: "free", points: [...], w }            the free pen
//   { type: "box" | "redact", x1, y1, x2, y2, w } a red box, a black-out bar
//   { type: "text", x, y, text, size, width, w }  a label; width is the measured text width

// Padding around a text label, as draw_text paints it
export function text_pad(s) {
	return s.size * 0.3;
}

// The rectangle a shape covers: { x1, y1, x2, y2 } with x1 <= x2, y1 <= y2
export function bounds(s) {
	if (s.type === "text") {
		const pad = text_pad(s);
		const width = s.width ?? s.text.length * s.size * 0.6; // measured on commit; a guess otherwise
		return { x1: s.x - pad, y1: s.y - pad, x2: s.x + width + pad, y2: s.y + s.size * 1.2 + pad };
	}
	if (s.type === "box" || s.type === "redact") {
		return {
			x1: Math.min(s.x1, s.x2),
			y1: Math.min(s.y1, s.y2),
			x2: Math.max(s.x1, s.x2),
			y2: Math.max(s.y1, s.y2),
		};
	}
	const xs = s.points.map((p) => p.x);
	const ys = s.points.map((p) => p.y);
	return { x1: Math.min(...xs), y1: Math.min(...ys), x2: Math.max(...xs), y2: Math.max(...ys) };
}

// distance from p to the segment a–b
function to_segment(p, a, b) {
	const dx = b.x - a.x;
	const dy = b.y - a.y;
	const len2 = dx * dx + dy * dy;
	const t = len2 ? Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / len2)) : 0;
	return Math.hypot(p.x - (a.x + t * dx), p.y - (a.y + t * dy));
}

function near_polyline(points, p, reach) {
	if (points.length === 1) return Math.hypot(p.x - points[0].x, p.y - points[0].y) <= reach;
	for (let i = 1; i < points.length; i++) {
		if (to_segment(p, points[i - 1], points[i]) <= reach) return true;
	}
	return false;
}

// True when p grabs the shape. Labels and black-out bars are grabbed anywhere on them; lines and
// boxes only near the line (tolerance plus half the line width), so one can still draw inside a box.
export function hit(s, p, tolerance) {
	if (s.type === "text" || s.type === "redact") {
		const b = bounds(s);
		return p.x >= b.x1 - tolerance && p.x <= b.x2 + tolerance && p.y >= b.y1 - tolerance && p.y <= b.y2 + tolerance;
	}
	const reach = tolerance + s.w / 2;
	if (s.type === "box") {
		const { x1, y1, x2, y2 } = bounds(s);
		const corners = [
			{ x: x1, y: y1 },
			{ x: x2, y: y1 },
			{ x: x2, y: y2 },
			{ x: x1, y: y2 },
			{ x: x1, y: y1 },
		];
		return near_polyline(corners, p, reach);
	}
	return near_polyline(s.points, p, reach);
}

// Index of the topmost (newest) shape under p, or -1
export function shape_at(shapes, p, tolerance) {
	for (let i = shapes.length - 1; i >= 0; i--) {
		if (hit(shapes[i], p, tolerance)) return i;
	}
	return -1;
}

// A copy of the shape, shifted by dx, dy
export function moved(s, dx, dy) {
	if (s.type === "text") return { ...s, x: s.x + dx, y: s.y + dy };
	if (s.type === "box" || s.type === "redact") {
		return { ...s, x1: s.x1 + dx, y1: s.y1 + dy, x2: s.x2 + dx, y2: s.y2 + dy };
	}
	return { ...s, points: s.points.map((p) => ({ x: p.x + dx, y: p.y + dy })) };
}

// Undo history over a shapes array, which it changes in place. Undo reverses the newest action;
// actions are undone newest first, so every index is valid again when its action is undone.
export class History {
	constructor(shapes) {
		this.shapes = shapes;
		this.actions = [];
	}

	// a shape that is already the last one of the array (drawn by the pointer) is kept
	added() {
		this.actions.push({ type: "add" });
	}

	add(shape) {
		this.shapes.push(shape);
		this.added();
	}

	remove(index) {
		const [shape] = this.shapes.splice(index, 1);
		this.actions.push({ type: "remove", index, shape });
	}

	// Moves and text edits. before: the shape as it was, when the array already holds the new one
	// (a drag updates it live). merge: a key; the same key on the same index right after joins the
	// previous step, so a run of arrow-key nudges is undone at once.
	replace(index, shape, { before, merge } = {}) {
		const last = this.actions[this.actions.length - 1];
		const old = before ?? this.shapes[index];
		this.shapes[index] = shape;
		if (merge && last && last.type === "replace" && last.merge === merge && last.index === index) return;
		this.actions.push({ type: "replace", index, before: old, merge });
	}

	// a merge run ends: the next nudge is a step of its own
	seal() {
		const last = this.actions[this.actions.length - 1];
		if (last) last.merge = undefined;
	}

	undo() {
		const action = this.actions.pop();
		if (!action) return false;
		if (action.type === "add") this.shapes.pop();
		else if (action.type === "remove") this.shapes.splice(action.index, 0, action.shape);
		else this.shapes[action.index] = action.before;
		return true;
	}
}
