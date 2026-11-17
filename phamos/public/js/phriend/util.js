// Small helpers shared by every Phriend module. No Desk or Vue globals in here: the same
// code runs in Desk and in the cockpits (phamos/phamos#1898).

export function storage_get(key, store = "local") {
	try {
		return window[`${store}Storage`].getItem(key);
	} catch (e) {
		return null; // private mode, blocked storage
	}
}

export function storage_set(key, value, store = "local") {
	try {
		if (value == null) window[`${store}Storage`].removeItem(key);
		else window[`${store}Storage`].setItem(key, value);
	} catch (e) {
		// not important enough to fail over
	}
}

export function sleep(ms) {
	return new Promise((resolve) => setTimeout(resolve, ms));
}

export function with_timeout(promise, ms, what = "Screenshot") {
	return new Promise((resolve, reject) => {
		const timer = setTimeout(() => {
			const error = new Error(`${what} timed out after ${ms} ms`);
			error.timed_out = true; // slow, not broken: callers may treat it differently
			reject(error);
		}, ms);
		promise.then(
			(value) => {
				clearTimeout(timer);
				resolve(value);
			},
			(error) => {
				clearTimeout(timer);
				reject(error);
			}
		);
	});
}

export function escape_html(text) {
	return String(text ?? "")
		.replace(/&/g, "&amp;")
		.replace(/</g, "&lt;")
		.replace(/>/g, "&gt;")
		.replace(/"/g, "&quot;")
		.replace(/'/g, "&#39;");
}

export function safe_json(value) {
	try {
		return JSON.stringify(value);
	} catch (e) {
		return String(value);
	}
}

// The host page's theme, so Phriend follows Desk's and the cockpits' dark mode.
export function host_theme() {
	const theme = document.documentElement.getAttribute("data-theme");
	if (theme === "dark" || theme === "light") return theme;
	return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function os_dark_query() {
	return window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
}

// Calls `apply` whenever the page's theme may have changed: Desk's or the cockpit's toggle
// (data-theme on <html>), and the OS switching between light and dark, which a page without
// data-theme follows (#1934).
export function watch_theme(apply, root = document.documentElement, os_dark = os_dark_query()) {
	new MutationObserver(apply).observe(root, { attributes: true, attributeFilter: ["data-theme"] });
	if (os_dark && os_dark.addEventListener) os_dark.addEventListener("change", apply);
}

function is_transparent(color) {
	if (!color || color === "transparent") return true;
	// rgba(0, 0, 0, 0) and rgb(0 0 0 / 0), as getComputedStyle reports an unset background;
	// only the alpha counts, so solid black rgb(0, 0, 0) is not transparent
	return /^rgba\((?:[^,]*,){3}\s*0(\.0*)?\s*\)$/.test(color) || /\/\s*0(\.0*)?\s*\)$/.test(color);
}

// The colour behind the page, for the screenshot: the first of the given computed backgrounds
// (body, then <html>) that isn't transparent. Neither set: white, or a dark grey in dark mode,
// so a dark page doesn't come out on white (#1934).
export function page_background(colors, theme) {
	const solid = colors.find((c) => !is_transparent(c));
	if (solid) return solid;
	return theme === "dark" ? "#171717" : "#ffffff";
}

// sessionStorage key for the text of a report that is not sent yet
export const DRAFT_KEY = "phriend:draft";

// "Chrome 142", "Safari 17": what a report needs, not the full user agent (GDPR review of !1162)
export function browser_name(ua) {
	if (!ua) return "";
	const match = ua.match(/(Edg|OPR|Firefox|Chrome|Version)\/(\d+)/) || ua.match(/(Safari)\/(\d+)/) || [];
	const names = { Edg: "Edge", OPR: "Opera", Version: "Safari" };
	const os = /Mac OS X/.test(ua) ? "macOS" : /Windows/.test(ua) ? "Windows" : /Android/.test(ua) ? "Android" : /iPhone|iPad/.test(ua) ? "iOS" : /Linux/.test(ua) ? "Linux" : "";
	return [match[1] ? `${names[match[1]] || match[1]} ${match[2]}` : "", os].filter(Boolean).join(", ");
}

// A URL without its query string and fragment: those can carry names and search terms.
export function without_query(url) {
	return String(url || "").split(/[?#]/)[0];
}
