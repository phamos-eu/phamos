// Drawing on the screenshot: arrow, free pen, box and text in red, and black bars over private data.
// The black bars are drawn into the image itself: what is under them is never sent. Plain DOM inside Phriend's Shadow
// DOM; the host (Desk or cockpit) has no part in it. Loaded on demand with the report flow.

import { escape_html } from "./util";

const RED = "#e5222b";

const ICONS = {
	pen: '<path d="M5 19 L19 5 M19 5 h-7 M19 5 v7"/>',
	draw: '<path d="M3 17 C6 9 9 6 10.5 9 S9 17 12.5 16 S17 6 21 7"/>',
	box: '<rect x="4.5" y="6.5" width="15" height="11" rx="1.5"/>',
	text: '<path d="M5 6 h14 M12 6 v13 M9 19 h6"/>',
	redact: '<rect x="3.5" y="8" width="17" height="8" rx="1.5" fill="currentColor"/>',
	undo: '<path d="M9 14 L4 9 L9 4"/><path d="M4 9 h10 a6 6 0 0 1 0 12 h-3"/>',
};

function icon(name) {
	return `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name]}</svg>`;
}

export class Annotator {
	// container: an element of the flow; screenshot: a canvas
	constructor(container, screenshot, __) {
		this.base = screenshot;
		this.shapes = [];
		this.tool = "pen";
		this.__ = __;

		container.innerHTML = `
			<div class="annotator">
				<div class="tools" role="toolbar" aria-label="${escape_html(__("Drawing tools"))}">
					<button type="button" class="tool on" data-tool="pen" title="${escape_html(__("Arrow"))}" aria-label="${escape_html(__("Arrow"))}" aria-pressed="true">${icon("pen")}</button>
					<button type="button" class="tool" data-tool="draw" title="${escape_html(__("Free drawing"))}" aria-label="${escape_html(__("Free drawing"))}" aria-pressed="false">${icon("draw")}</button>
					<button type="button" class="tool" data-tool="box" title="${escape_html(__("Box"))}" aria-label="${escape_html(__("Box"))}" aria-pressed="false">${icon("box")}</button>
					<button type="button" class="tool" data-tool="text" title="${escape_html(__("Text"))}" aria-label="${escape_html(__("Text"))}" aria-pressed="false">${icon("text")}</button>
					<button type="button" class="tool" data-tool="redact" title="${escape_html(__("Black out private data"))}" aria-label="${escape_html(__("Black out private data"))}" aria-pressed="false">${icon("redact")}</button>
					<span class="tool-gap"></span>
					<button type="button" class="tool" data-action="undo" title="${escape_html(__("Undo"))}" aria-label="${escape_html(__("Undo"))}">${icon("undo")}</button>
				</div>
				<div class="canvas-wrap"><canvas></canvas></div>
			</div>`;

		this.canvas = container.querySelector("canvas");
		this.canvas.width = screenshot.width;
		this.canvas.height = screenshot.height;
		this.ctx = this.canvas.getContext("2d");
		this.wrap = container.querySelector(".canvas-wrap");

		container.querySelectorAll("[data-tool]").forEach((button) =>
			button.addEventListener("click", () => {
				this.commit_text();
				this.tool = button.dataset.tool;
				this.canvas.style.cursor = this.tool === "text" ? "text" : "crosshair";
				container.querySelectorAll("[data-tool]").forEach((b) => {
					b.classList.toggle("on", b === button);
					b.setAttribute("aria-pressed", b === button ? "true" : "false");
				});
			})
		);
		container.querySelector("[data-action=undo]").addEventListener("click", () => this.undo());

		this.bind_drawing();
		this.redraw();
	}

	has_drawing() {
		return this.shapes.length > 0 || !!this.editing;
	}

	undo() {
		if (this.cancel_text()) return; // the text box you're typing in goes first
		this.shapes.pop();
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

	bind_drawing() {
		let current = null;
		this.canvas.addEventListener("pointerdown", (e) => {
			if (this.tool === "text") {
				e.preventDefault(); // keep the focus for the text box we're about to open
				this.commit_text();
				this.start_text(e);
				return;
			}
			this.canvas.setPointerCapture(e.pointerId);
			const p = this.point(e);
			const w = 4 * this.scale();
			if (this.tool === "box" || this.tool === "redact") {
				current = { type: this.tool, x1: p.x, y1: p.y, x2: p.x, y2: p.y, w };
			} else if (this.tool === "draw") {
				current = { type: "free", points: [p], w }; // follows the pointer
			} else {
				current = { type: "pen", points: [p, { ...p }], w }; // a straight arrow
			}
			this.shapes.push(current);
		});
		this.canvas.addEventListener("pointermove", (e) => {
			if (!current) return;
			const p = this.point(e);
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
			// a click without dragging leaves nothing behind; a black-out bar may be as small as
			// one character, so only a bare click is dropped there
			const min = current && current.type === "redact" ? current.w / 2 : current && current.w * 2;
			if (current && this.size_of(current) < min) {
				this.shapes.pop();
				this.redraw();
			}
			current = null;
		};
		this.canvas.addEventListener("pointerup", stop);
		this.canvas.addEventListener("pointercancel", stop);
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

	start_text(e) {
		const rect = this.canvas.getBoundingClientRect();
		const wrap = this.wrap.getBoundingClientRect();
		const x = e.clientX - rect.left;
		const y = e.clientY - rect.top;
		const input = document.createElement("input");
		input.type = "text";
		input.className = "text-input";
		input.placeholder = this.__("Type here…");
		input.style.left = `${e.clientX - wrap.left + this.wrap.scrollLeft}px`;
		input.style.top = `${e.clientY - wrap.top + this.wrap.scrollTop}px`;
		this.wrap.appendChild(input);
		this.editing = { input, x: x * this.scale(), y: y * this.scale() };

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
		ctx.strokeStyle = RED;
		ctx.lineCap = "round";
		ctx.lineJoin = "round";
		this.shapes.forEach((s) => {
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
		return this.canvas;
	}
}
