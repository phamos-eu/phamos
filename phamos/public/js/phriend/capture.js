// Takes the screenshot. html2canvas first (0.2–0.5 s on our pages), html-to-image when it
// fails. Both re-draw the page in JavaScript, so Phriend leaves out what can't be seen.
// Loaded on demand with the report flow.

import html2canvas from "html2canvas";
import { toCanvas as html_to_canvas } from "html-to-image";
import { host_theme, page_background, sleep, storage_get, storage_set, with_timeout } from "./util";

const HTML2CANVAS_TIMEOUT_MS = 3000; // then html-to-image
const CAPTURE_TIMEOUT_MS = 8000; // both engines together; then the flow goes on without one
// Remembers per page type that html2canvas failed there, so the slow failure happens once.
// Only real errors count, not a slow run, and the memo expires: the page or the browser may
// have changed since. v5: v4 memos were also written on timeouts, so they are ignored.
const ENGINE_KEY_PREFIX = "phriend:engine:v5:";
const ENGINE_MEMO_DAYS = 7;
const DEBUG_KEY = "phriend:debug"; // localStorage.setItem("phriend:debug", 1) for html2canvas logs
const KEEP_TAGS = new Set(["HEAD", "LINK", "STYLE", "META", "TITLE", "BASE"]);
const BLANK_GIF = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7";

// Phriend itself, toasts and screen-reader-only text never belong in the screenshot.
function is_excluded(el) {
	return (
		el.id === "phriend-root" ||
		el.id === "alert-container" ||
		(el.classList && ["phriend-ignore", "sr-only", "visually-hidden"].some((c) => el.classList.contains(c))) ||
		(el.getAttribute && el.getAttribute("role") === "status" && el.hasAttribute("aria-live"))
	);
}

// Hidden pages (Frappe keeps every page you visited in the DOM), the icon sprite, and anything
// outside the window: copying those was ~90% of the capture time.
//
// `before_too`: also skip what lies above or left of the window. Right for html2canvas, which
// only leaves those out of the drawing. html-to-image removes what it skips from its copy of
// the page, so the content below would move up into their place: it may only skip what comes
// after the window.
function is_off_screen(el, before_too) {
	if (!el.getBoundingClientRect || el === document.body || el === document.documentElement) return false;
	if (KEEP_TAGS.has(el.tagName) || el.parentNode === document.head) return false; // the page's CSS
	const r = el.getBoundingClientRect();
	if (r.width === 0 && r.height === 0) {
		return el.tagName.toLowerCase() === "svg" || getComputedStyle(el).display === "none";
	}
	const after = r.top > window.innerHeight || r.left > window.innerWidth;
	const before = r.bottom < 0 || r.right < 0;
	const outside = after || (before_too && before);
	return outside && !el.querySelector(".modal.show, .modal-backdrop"); // may hold an open dialog
}

function skip(el) {
	return is_excluded(el) || is_off_screen(el, true);
}

function skip_for_copy(el) {
	return is_excluded(el) || is_off_screen(el, false);
}

function background() {
	const of = (el) => getComputedStyle(el).backgroundColor;
	return page_background([of(document.body), of(document.documentElement)], host_theme());
}

function render_html2canvas() {
	return html2canvas(document.body, {
		logging: !!storage_get(DEBUG_KEY),
		x: window.scrollX,
		y: window.scrollY,
		width: window.innerWidth,
		height: window.innerHeight,
		windowWidth: window.innerWidth,
		windowHeight: window.innerHeight,
		scale: 1, // 2x is ~4x the work and freezes heavy pages
		useCORS: true,
		imageTimeout: 1500, // don't hang on a slow avatar
		backgroundColor: background(),
		ignoreElements: skip,
	});
}

// html-to-image copies the page without scroll positions: the copy shows every container
// scrolled to the top. The cockpits scroll inside one (not the window), so it drew the wrong
// part of the page. Before copying, Phriend
//   1. decides what to leave out (only what comes after the window, see is_off_screen),
//   2. pins sticky elements where the user sees them (in the copy nothing scrolls, so
//      "sticky" would put them back at their place in the flow),
//   3. shifts the content of every scrolled container by its scroll offset.
// The live page is covered by the report flow meanwhile, and everything is put back after.
function prepare_copy() {
	const skipped = new Set();
	const sticky = [];
	const walk = (el) => {
		for (const child of el.children) {
			if (skip_for_copy(child)) {
				skipped.add(child);
				continue;
			}
			if (getComputedStyle(child).position === "sticky") sticky.push(child);
			walk(child);
		}
	};
	walk(document.body);

	const changed = []; // [element, inline position, inline translate]
	const offsets = new Map(); // element -> [x, y] to add
	const add = (el, x, y) => {
		const [ox, oy] = offsets.get(el) || [0, 0];
		offsets.set(el, [ox + x, oy + y]);
	};

	// measure all sticky elements first: switching one changes where the next one is
	const stuck = sticky.map((el) => el.getBoundingClientRect());
	sticky.forEach((el) => {
		changed.push([el, el.style.position, el.style.translate]);
		el.style.position = "relative";
	});
	sticky.forEach((el, i) => {
		const natural = el.getBoundingClientRect();
		add(el, stuck[i].left - natural.left, stuck[i].top - natural.top);
	});

	for (const el of document.body.querySelectorAll("*")) {
		if ((el.scrollTop || el.scrollLeft) && !skipped.has(el)) {
			for (const child of el.children) add(child, -el.scrollLeft, -el.scrollTop);
		}
	}
	offsets.forEach(([x, y], el) => {
		if (!sticky.includes(el)) changed.push([el, el.style.position, el.style.translate]);
		const [tx, ty] = current_translate(el); // add to a translate the page already has
		el.style.translate = `${tx + x}px ${ty + y}px`;
	});

	let restored = false;
	const restore = () => {
		if (restored) return; // from the timeout and from html-to-image finishing late
		restored = true;
		changed.forEach(([el, position, translate]) => {
			el.style.position = position;
			el.style.translate = translate;
		});
	};
	return { skipped, restore };
}

function current_translate(el) {
	const value = getComputedStyle(el).translate;
	if (!value || value === "none") return [0, 0];
	const [x = "0", y = "0"] = value.split(" ");
	return [parseFloat(x) || 0, parseFloat(y) || 0];
}

// `ms`: html-to-image can hang on an image that never loads. The page must not stay shifted,
// so it gets its own deadline and the page is put back when it passes.
async function render_html_to_image(ms) {
	const { skipped, restore } = prepare_copy();
	const copy = html_to_canvas(document.body, {
		width: window.innerWidth,
		height: window.innerHeight,
		pixelRatio: 1,
		skipFonts: true, // embedding every web font is the slowest part
		backgroundColor: background(),
		filter: (node) => !(node.nodeType === 1 && skipped.has(node)),
		imagePlaceholder: BLANK_GIF,
		style: {
			transform: `translate(${-window.scrollX}px, ${-window.scrollY}px)`,
			transformOrigin: "0 0",
		},
	});
	copy.finally(restore).catch(() => {});
	try {
		return await with_timeout(copy, ms);
	} finally {
		restore();
	}
}

function html2canvas_failed_here(memo) {
	try {
		const { at } = JSON.parse(storage_get(memo) || "null") || {};
		return !!at && Date.now() - at < ENGINE_MEMO_DAYS * 86400000;
	} catch (e) {
		return false; // a broken value: try html2canvas again
	}
}

async function render(engine_key, deadline) {
	const memo = `${ENGINE_KEY_PREFIX}${engine_key}`;
	const left = () => Math.max(0, deadline - performance.now());
	if (html2canvas_failed_here(memo)) return render_html_to_image(left());
	try {
		return await with_timeout(render_html2canvas(), Math.min(HTML2CANVAS_TIMEOUT_MS, left()));
	} catch (e) {
		console.warn("Phriend: html2canvas failed, trying html-to-image", e);
		if (!(e && e.timed_out)) storage_set(memo, JSON.stringify({ at: Date.now() }));
		return render_html_to_image(left());
	}
}

// Returns { canvas, ms }. Rejects after CAPTURE_TIMEOUT_MS.
export async function capture(engine_key) {
	// Frappe draws ::before/::after on grid checkboxes; html2canvas reads an empty style there
	// and crashes ("Error parsing CSS component value"). And many elements have
	// "transition: all": the shifts in prepare_copy would animate, and the copy would catch
	// them at the start. Both are switched off while we draw (Phriend's own Shadow DOM keeps
	// its styles).
	const fix = document.createElement("style");
	fix.textContent =
		"input::before,input::after,textarea::before,textarea::after,select::before,select::after{content:none!important}" +
		"*,*::before,*::after{transition:none!important}";
	document.head.appendChild(fix);
	await sleep(30); // a timer, not requestAnimationFrame: that pauses in background tabs
	const started = performance.now();
	try {
		const canvas = await render(engine_key, started + CAPTURE_TIMEOUT_MS);
		// a page of 0 x 0 pixels (a hidden or minimised window) draws nothing to send
		if (!canvas || !canvas.width || !canvas.height) throw new Error("The screenshot is empty");
		return { canvas, ms: Math.round(performance.now() - started) };
	} finally {
		fix.remove();
	}
}

// The smaller of PNG and JPEG: JPEG is 35–60% smaller on our pages, PNG wins on plain ones.
// null when the canvas can't be encoded (empty, or larger than the browser allows: "data:,").
export function to_data_url(canvas) {
	const png = canvas.toDataURL("image/png");
	const jpeg = canvas.toDataURL("image/jpeg", 0.85);
	const smaller = jpeg.length < png.length ? jpeg : png;
	return smaller.startsWith("data:image/") ? smaller : null;
}
