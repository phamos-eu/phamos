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

// sessionStorage key for the text of a report that is not sent yet
export const DRAFT_KEY = "phriend:draft";
