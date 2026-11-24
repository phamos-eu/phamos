// Phriend on the website pages (phamos/phamos#2104): the loader, on every website page.
//
// Kept tiny on purpose: visitors and portal logins get nothing more than this. Only when the
// `system_user` cookie says Desk user, it asks the server whether Phriend is for this user
// (phamos.phriend.api.get_web_boot: Phriend Settings → Enabled, Allowed role, Desk users only)
// and then loads the ball itself (phriend_web_app.bundle.js) with a script tag.

const BOOT_METHOD = "phamos.phriend.api.get_web_boot";
const APP_BUNDLE = "phriend_web_app.bundle.js";

function is_desk_user() {
	return /(?:^|;\s*)system_user=yes(?:;|$)/.test(document.cookie || "");
}

// The hashed URL of a phamos bundle; the website boot carries the asset map (frappe.boot.assets_json).
function asset_url(name) {
	const assets = (window.frappe && frappe.boot && frappe.boot.assets_json) || {};
	return assets[name] || null;
}

function load_script(src) {
	return new Promise((resolve, reject) => {
		const script = document.createElement("script");
		script.src = src;
		script.onload = resolve;
		script.onerror = () => {
			script.remove();
			reject(new Error(`Could not load ${src}`));
		};
		document.head.appendChild(script);
	});
}

async function start() {
	if (!is_desk_user() || window.phriend_web_boot !== undefined) return;
	window.phriend_web_boot = null; // once per page
	const src = asset_url(APP_BUNDLE);
	if (!src) return;
	const response = await fetch(`/api/method/${BOOT_METHOD}`, {
		credentials: "same-origin",
		headers: { Accept: "application/json" },
	});
	if (!response.ok) return;
	const boot = (await response.json()).message;
	if (!boot || !boot.enabled) return;
	window.phriend_web_boot = boot;
	await load_script(src);
}

// a website page must never break because of Phriend
const run = () => start().catch((e) => console.warn("Phriend:", e));
if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", run);
else run();
