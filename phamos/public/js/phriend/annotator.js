// Drawing on the screenshot: arrow, free pen, box and text in red, and black bars over private data.
// The black bars are drawn into the image itself: what is under them is never sent. Plain DOM inside Phriend's Shadow
// DOM; the host (Desk or cockpit) has no part in it. Loaded on demand with the report flow.
// Any drawing can be grabbed with any tool: press on it to select and drag it, Delete removes it,
// double-click edits a text, the arrow keys nudge it, Undo reverses the last action (shapes.js).

import { IS_MAC } from "./shortcut";
import { History, bounds, moved, shape_at } from "./shapes";
import { escape_html } from "./util";

// screen pixels around a drawing that still grab it
const GRAB = 6;

// A letter per tool, for the keyboard (flow.js shot_key); shown in the tooltips
const TOOL_KEYS = { a: "pen", p: "draw", b: "box", t: "text", x: "redact" };

const RED = "#e5222b";

const ICONS = {
	pen: '<path d="M5 19 L19 5 M19 5 h-7 M19 5 v7"/>',
	draw: '<path d="M3 17 C6 9 9 6 10.5 9 S9 17 12.5 16 S17 6 21 7"/>',
	box: '<rect x="4.5" y="6.5" width="15" height="11" rx="1.5"/>',
	text: '<path d="M5 6 h14 M12 6 v13 M9 19 h6"/>',
	redact: '<rect x="3.5" y="8" width="17" height="8" rx="1.5" fill="currentColor"/>',
	undo: '<path d="M9 14 L4 9 L9 4"/><path d="M4 9 h10 a6 6 0 0 1 0 12 h-3"/>',
	trash: '<path d="M4 7 h16 M10 7 V4.5 h4 V7 M6.5 7 l1 12.5 h9 l1 -12.5 M10 11 v5 M14 11 v5"/>',
};

function icon(name) {
	return `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name]}</svg>`;
}

export class Annotator {
	// container: an element of the flow; screenshot: a canvas
	constructor(container, screenshot, __) {
		this.base = screenshot;
		this.shapes = [];
		this.history = new History(this.shapes);
		this.selected = -1; // index into shapes, -1: nothing selected
		this.pressing = false; // a drawing is being made or dragged: Undo, Delete and nudges wait
		this.tool = "pen";
		this.__ = __;

		container.innerHTML = `
			<div class="annotator">
				<div class="tools" role="toolbar" aria-label="${escape_html(__("Drawing tools"))}">
					<button type="button" class="tool on" data-tool="pen" title="${escape_html(__("Arrow"))} (A)" aria-label="${escape_html(__("Arrow"))}" aria-keyshortcuts="A" aria-pressed="true">${icon("pen")}</button>
					<button type="button" class="tool" data-tool="draw" title="${escape_html(__("Free drawing"))} (P)" aria-label="${escape_html(__("Free drawing"))}" aria-keyshortcuts="P" aria-pressed="false">${icon("draw")}</button>
					<button type="button" class="tool" data-tool="box" title="${escape_html(__("Box"))} (B)" aria-label="${escape_html(__("Box"))}" aria-keyshortcuts="B" aria-pressed="false">${icon("box")}</button>
					<button type="button" class="tool" data-tool="text" title="${escape_html(__("Text"))} (T)" aria-label="${escape_html(__("Text"))}" aria-keyshortcuts="T" aria-pressed="false">${icon("text")}</button>
					<button type="button" class="tool" data-tool="redact" title="${escape_html(__("Black out private data"))} (X)" aria-label="${escape_html(__("Black out private data"))}" aria-keyshortcuts="X" aria-pressed="false">${icon("redact")}</button>
					<span class="tool-gap"></span>
					<button type="button" class="tool" data-action="undo" title="${escape_html(__("Undo"))} (${IS_MAC ? "⌘Z" : "Ctrl+Z"})" aria-label="${escape_html(__("Undo"))}">${icon("undo")}</button>
					<button type="button" class="tool" data-action="delete" title="${escape_html(__("Delete"))} (${IS_MAC ? "⌫" : escape_html(__("Del"))})" aria-label="${escape_html(__("Delete"))}" aria-keyshortcuts="Delete Backspace" disabled>${icon("trash")}</button>
				</div>
				<div class="canvas-wrap"><canvas></canvas></div>
			</div>`;

		this.canvas = container.querySelector("canvas");
		this.canvas.width = screenshot.width;
		this.canvas.height = screenshot.height;
		this.ctx = this.canvas.getContext("2d");
		this.wrap = container.querySelector(".canvas-wrap");

		this.container = container;
		container.querySelectorAll("[data-tool]").forEach((button) =>
			button.addEventListener("click", () => this.select_tool(button.dataset.tool))
		);
		container.querySelector("[data-action=undo]").addEventListener("click", () => this.undo());
		this.delete_button = container.querySelector("[data-action=delete]");
		this.delete_button.addEventListener("click", () => this.delete_selected());

		this.bind_drawing();
		this.redraw();
	}

	select_tool(tool) {
		this.commit_text();
		this.clear_selection();
		this.tool = tool;
		this.canvas.style.cursor = this.tool_cursor();
		this.container.querySelectorAll("[data-tool]").forEach((b) => {
			const on = b.dataset.tool === tool;
			b.classList.toggle("on", on);
			b.setAttribute("aria-pressed", on ? "true" : "false");
		});
	}

	// True when the key picks a tool
	select_tool_by_key(key) {
		const tool = TOOL_KEYS[key];
		if (!tool) return false;
		this.select_tool(tool);
		return true;
	}

	has_drawing() {
		return this.shapes.length > 0 || !!this.editing;
	}

	tool_cursor() {
		return this.tool === "text" ? "text" : "crosshair";
	}

	// the last action: a drawing, a move, a delete or a text edit
	undo() {
		if (this.cancel_text()) return; // the text box you're typing in goes first
		if (this.pressing) return; // the pointer still holds a drawing; its index must stay valid
		this.history.undo();
		this.select(-1);
	}

	// ---- selection: press on a drawing with any tool

	select(index) {
		this.history.seal(); // nudges after a new selection are a new undo step
		this.selected = index;
		this.delete_button.disabled = index < 0;
		this.redraw();
	}

	// True when something was selected (Escape is used up by it then, flow.js)
	clear_selection() {
		if (this.selected < 0) return false;
		this.select(-1);
		return true;
	}

	// True when a drawing was deleted
	delete_selected() {
		if (this.selected < 0 || this.pressing) return false;
		this.history.remove(this.selected);
		this.select(-1);
		return true;
	}

	// Arrow keys: a screen pixel, ten with Shift. A run of nudges is one undo step.
	// True when a drawing was selected to nudge.
	nudge(key, big) {
		const dir = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[key];
		if (!dir || this.selected < 0 || this.pressing) return false;
		const step = this.scale() * (big ? 10 : 1);
		const i = this.selected;
		this.history.replace(i, moved(this.shapes[i], dir[0] * step, dir[1] * step), { merge: "nudge" });
		this.redraw();
		return true;
	}

	grab_tolerance() {
		return GRAB * this.scale();
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

	bind_drawing() {
		let current = null; // a drawing being made
		let drag = null; // a drawing being moved: { index, from, before, moved }
		this.canvas.addEventListener("pointerdown", (e) => {
			this.commit_text(); // a text being typed is placed first
			const p = this.point(e);
			const index = shape_at(this.shapes, p, this.grab_tolerance());
			if (index >= 0) {
				// any tool grabs a drawing that is already there
				e.preventDefault();
				this.canvas.setPointerCapture(e.pointerId);
				drag = { index, from: p, before: this.shapes[index], moved: false };
				this.pressing = true;
				this.select(index);
				return;
			}
			this.clear_selection();
			if (this.tool === "text") {
				e.preventDefault(); // keep the focus for the text box we're about to open
				this.start_text(p);
				return;
			}
			this.canvas.setPointerCapture(e.pointerId);
			const w = 4 * this.scale();
			if (this.tool === "box" || this.tool === "redact") {
				current = { type: this.tool, x1: p.x, y1: p.y, x2: p.x, y2: p.y, w };
			} else if (this.tool === "draw") {
				current = { type: "free", points: [p], w }; // follows the pointer
			} else {
				current = { type: "pen", points: [p, { ...p }], w }; // a straight arrow
			}
			this.shapes.push(current);
			this.pressing = true;
		});
		this.canvas.addEventListener("pointermove", (e) => {
			const p = this.point(e);
			if (drag) {
				const dx = p.x - drag.from.x;
				const dy = p.y - drag.from.y;
				drag.moved = drag.moved || dx !== 0 || dy !== 0;
				this.shapes[drag.index] = moved(drag.before, dx, dy);
				this.redraw();
				return;
			}
			if (!current) {
				// the move cursor shows what a press would grab
				const over = shape_at(this.shapes, p, this.grab_tolerance()) >= 0;
				this.canvas.style.cursor = over ? "move" : this.tool_cursor();
				return;
			}
			if (current.type === "box" || current.type === "redact") {
				current.x2 = p.x;
				current.y2 = p.y;
			} else if (current.type === "free") {
				// every point the browser saw since the last event, not only the last one, so fast
				// strokes stay smooth; points closer than a screen pixel add nothing
				const events = e.getCoalescedEvents ? e.getCoalescedEvents() : [e];
				const step = this.scale();
				for (const ev of events.length ? events : [e]) {
					const q = this.point(ev);
					const last = current.points[current.points.length - 1];
					if (Math.hypot(q.x - last.x, q.y - last.y) >= step) current.points.push(q);
				}
			} else {
				current.points[1] = p;
			}
			this.redraw();
		});
		const stop = () => {
			this.pressing = false;
			if (drag) {
				// a press without a move only selects: no undo step
				if (drag.moved) this.history.replace(drag.index, this.shapes[drag.index], { before: drag.before });
				else this.shapes[drag.index] = drag.before;
				drag = null;
				return;
			}
			if (!current) return;
			// a click without dragging leaves nothing behind; a black-out bar may be as small as
			// one character, so only a bare click is dropped there
			const min = current.type === "redact" ? current.w / 2 : current.w * 2;
			if (this.size_of(current) < min) {
				this.shapes.pop();
				this.redraw();
			} else {
				this.history.added();
			}
			current = null;
		};
		this.canvas.addEventListener("pointerup", stop);
		this.canvas.addEventListener("pointercancel", stop);
		// double-click on a text opens it for editing, with any tool
		this.canvas.addEventListener("dblclick", (e) => {
			const index = shape_at(this.shapes, this.point(e), this.grab_tolerance());
			if (index < 0 || this.shapes[index].type !== "text") return;
			e.preventDefault();
			this.select(-1);
			this.start_text(this.shapes[index], this.shapes[index].text, index);
		});
	}

	size_of(s) {
		if (s.type === "box" || s.type === "redact") return Math.max(Math.abs(s.x2 - s.x1), Math.abs(s.y2 - s.y1));
		if (s.type === "free") {
			const xs = s.points.map((p) => p.x);
			const ys = s.points.map((p) => p.y);
			return Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys));
		}
		const [a, b] = s.points;
		return Math.hypot(b.x - a.x, b.y - a.y);
	}

	// ---- text: click on the screenshot, type, Enter (or click away) to place it

	font(size) {
		return `600 ${size}px Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`;
	}

	text_width(size, text) {
		const ctx = this.ctx;
		ctx.save();
		ctx.font = this.font(size);
		const width = ctx.measureText(text).width;
		ctx.restore();
		return width;
	}

	// Opens the text box at p (screenshot pixels). index: the text drawing it edits, -1 for a new one.
	start_text(p, value = "", index = -1) {
		const scale = this.scale();
		const rect = this.canvas.getBoundingClientRect();
		const wrap = this.wrap.getBoundingClientRect();
		const input = document.createElement("input");
		input.type = "text";
		input.className = "text-input";
		input.placeholder = this.__("Type here…");
		input.value = value;
		input.style.left = `${rect.left - wrap.left + this.wrap.scrollLeft + p.x / scale}px`;
		input.style.top = `${rect.top - wrap.top + this.wrap.scrollTop + p.y / scale}px`;
		this.wrap.appendChild(input);
		this.editing = { input, x: p.x, y: p.y, index };
		if (index >= 0) this.redraw(); // the text box stands in for the drawing while it is edited

		input.addEventListener("keydown", (ev) => {
			ev.stopPropagation(); // Enter and Escape belong to the text box, not to the flow
			if (ev.key === "Enter") {
				ev.preventDefault();
				this.commit_text();
			} else if (ev.key === "Escape") {
				ev.preventDefault();
				this.cancel_text();
			}
		});
		input.addEventListener("blur", () => this.commit_text());
		setTimeout(() => input.focus({ preventScroll: true }), 0); // a text box near the edge doesn't scroll the screenshot
	}

	// Places the text. An edited text that is emptied is deleted; one left as it was adds no undo step.
	commit_text() {
		const editing = this.editing;
		if (!editing) return;
		this.editing = null;
		const text = editing.input.value.trim();
		editing.input.remove();
		if (editing.index >= 0) {
			const s = this.shapes[editing.index];
			if (!text) this.history.remove(editing.index);
			else if (text !== s.text) {
				this.history.replace(editing.index, { ...s, text, width: this.text_width(s.size, text) });
			}
			this.redraw();
			return;
		}
		if (!text) return;
		const scale = this.scale();
		const size = 18 * scale;
		this.history.add({
			type: "text",
			x: editing.x,
			y: editing.y,
			text,
			size,
			width: this.text_width(size, text),
			w: 4 * scale,
		});
		this.redraw();
	}

	// Escape: a new text is dropped, an edited one keeps its old text
	cancel_text() {
		if (!this.editing) return false;
		const { input, index } = this.editing;
		this.editing = null;
		input.remove();
		if (index >= 0) this.redraw();
		return true;
	}

	redraw() {
		const ctx = this.ctx;
		ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
		ctx.drawImage(this.base, 0, 0);
		ctx.strokeStyle = RED;
		ctx.lineCap = "round";
		ctx.lineJoin = "round";
		const hidden = this.editing ? this.editing.index : -1;
		this.shapes.forEach((s, i) => {
			if (i === hidden) return;
			ctx.lineWidth = s.w;
			if (s.type === "redact") {
				this.draw_redaction(s);
			} else if (s.type === "text") {
				this.draw_text(s);
			} else if (s.type === "free") {
				this.draw_free(s);
			} else if (s.type === "box") {
				ctx.strokeRect(Math.min(s.x1, s.x2), Math.min(s.y1, s.y2), Math.abs(s.x2 - s.x1), Math.abs(s.y2 - s.y1));
			} else {
				ctx.beginPath();
				s.points.forEach((p, i) => (i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y)));
				ctx.stroke();
				this.arrow_head(s);
			}
		});
		const selected = this.shapes[this.selected];
		if (selected && this.selected !== hidden) this.draw_selection(selected);
	}

	// A dashed frame around the selected drawing, white and dark dashes in turn, so it shows on
	// any screenshot. On screen only: result() clears the selection before the image is sent.
	draw_selection(s) {
		const ctx = this.ctx;
		const scale = this.scale();
		const pad = (GRAB / 2) * scale + s.w / 2;
		const b = bounds(s);
		const dash = 5 * scale;
		ctx.save();
		ctx.lineWidth = 1.5 * scale;
		ctx.setLineDash([dash, dash]);
		[
			["#ffffff", 0],
			["#1f2328", dash],
		].forEach(([colour, offset]) => {
			ctx.strokeStyle = colour;
			ctx.lineDashOffset = offset;
			ctx.strokeRect(b.x1 - pad, b.y1 - pad, b.x2 - b.x1 + 2 * pad, b.y2 - b.y1 + 2 * pad);
		});
		ctx.restore();
	}

	// A black bar that can't be mistaken for something black on the page: fine diagonal stripes,
	// a small light Phriend and "REDACTED". The label shrinks to fit, and is left out when the
	// bar is too small for it (the stripes still show it was blacked out).
	draw_redaction(s) {
		const ctx = this.ctx;
		// whole pixels, rounded outward: no edge pixel of the screenshot blends through
		const x = Math.floor(Math.min(s.x1, s.x2));
		const y = Math.floor(Math.min(s.y1, s.y2));
		const w = Math.ceil(Math.max(s.x1, s.x2)) - x;
		const h = Math.ceil(Math.max(s.y1, s.y2)) - y;
		const unit = s.w / 4; // screenshot pixels per screen pixel when it was drawn

		ctx.save();
		ctx.beginPath();
		ctx.rect(x, y, w, h);
		ctx.clip();
		ctx.fillStyle = "#111";
		ctx.fillRect(x, y, w, h);
		ctx.strokeStyle = "rgba(255, 255, 255, 0.07)";
		ctx.lineWidth = 3 * unit;
		ctx.beginPath();
		for (let d = -h; d < w; d += 10 * unit) {
			ctx.moveTo(x + d, y + h);
			ctx.lineTo(x + d + h, y);
		}
		ctx.stroke();

		const text = this.__("Redacted").toLocaleUpperCase();
		const pad = 6 * unit;
		let size = Math.min(h * 0.5, 13 * unit);
		ctx.font = `700 ${size}px Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`;
		const spacing = "letterSpacing" in ctx; // not in older Safari and Firefox
		const spaced = () => ctx.measureText(text).width + (spacing ? text.length * size * 0.08 : 0);
		let total = size * 1.2 + size * 0.5 + spaced(); // Phriend, gap, text
		if (total > w - 2 * pad) {
			size *= (w - 2 * pad) / total;
			ctx.font = `700 ${size}px Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`;
			total = size * 1.2 + size * 0.5 + spaced();
		}
		if (size >= 6 * unit) {
			const left = x + (w - total) / 2;
			const mid = y + h / 2;
			this.draw_mini_phriend(left + size * 0.6, mid, size * 0.6);
			ctx.fillStyle = "rgba(255, 255, 255, 0.82)";
			ctx.textBaseline = "middle";
			if (spacing) ctx.letterSpacing = `${size * 0.08}px`;
			ctx.fillText(text, left + size * 1.7, mid + size * 0.05);
		} else if (Math.min(w, h) >= 10 * unit) {
			this.draw_mini_phriend(x + w / 2, y + h / 2, Math.min(w, h) * 0.3); // just the mark
		}
		ctx.restore();
	}

	// Phriend in negative (light ball, dark eyes), so it shows on the black bar.
	draw_mini_phriend(cx, cy, r) {
		const ctx = this.ctx;
		ctx.fillStyle = "rgba(255, 255, 255, 0.82)";
		ctx.beginPath();
		ctx.arc(cx, cy, r, 0, Math.PI * 2);
		ctx.fill();
		ctx.fillStyle = "#111";
		[-0.33, 0.33].forEach((dx) => {
			ctx.beginPath();
			ctx.ellipse(cx + dx * r, cy - 0.08 * r, 0.16 * r, 0.22 * r, 0, 0, Math.PI * 2);
			ctx.fill();
		});
	}

	// A freehand line, smoothed: through the midpoints between the points, with the points as
	// control points, so the corners of the pointer path don't show.
	draw_free(s) {
		const ctx = this.ctx;
		const pts = s.points;
		ctx.beginPath();
		ctx.moveTo(pts[0].x, pts[0].y);
		if (pts.length < 3) {
			pts.slice(1).forEach((p) => ctx.lineTo(p.x, p.y));
		} else {
			for (let i = 1; i < pts.length - 1; i++) {
				const mid = { x: (pts[i].x + pts[i + 1].x) / 2, y: (pts[i].y + pts[i + 1].y) / 2 };
				ctx.quadraticCurveTo(pts[i].x, pts[i].y, mid.x, mid.y);
			}
			const end = pts[pts.length - 1];
			ctx.lineTo(end.x, end.y);
		}
		ctx.stroke();
	}

	// red text on a white label, so it reads on any background
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
		ctx.fillStyle = RED;
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
		ctx.fillStyle = RED;
		ctx.fill();
	}

	// the screenshot with the drawing
	result() {
		this.commit_text(); // still typing when Send was clicked
		this.clear_selection(); // no selection frame in the sent image
		return this.canvas;
	}
}
