// Phriend's keyboard shortcut (#1900), in the notation phamos/phriend/shortcut.py keeps:
// modifiers then one key, e.g. "Mod+P" or "Alt+Shift+P". "Mod" is Cmd on a Mac, Ctrl elsewhere.
// Pure functions, tested in shortcut.test.js.

export const IS_MAC =
	typeof navigator !== "undefined" && /Mac|iPhone|iPad|iPod/i.test(navigator.platform || navigator.userAgent || "");

const MODIFIERS = ["Mod", "Ctrl", "Alt", "Shift"];
const KEY = /^([A-Z0-9]|F([1-9]|1[0-2])|Space)$/;

// "Mod+Shift+P" -> { mod, ctrl, alt, shift, key }; null for "" or anything unreadable
export function parse(text) {
	if (!text) return null;
	const spec = { mod: false, ctrl: false, alt: false, shift: false, key: null };
	for (const part of String(text).split("+")) {
		const name = part.trim();
		if (MODIFIERS.includes(name)) spec[name.toLowerCase()] = true;
		else if (!spec.key && KEY.test(name)) spec.key = name;
		else return null;
	}
	return spec.key ? spec : null;
}

// The key of a keyboard event by its position (event.code), so Option on a Mac, which changes
// event.key ("∏" for Option+Shift+P), doesn't matter.
export function key_of(event) {
	const code = event.code || "";
	if (/^Key[A-Z]$/.test(code)) return code.slice(3);
	if (/^Digit[0-9]$/.test(code)) return code.slice(5);
	if (/^F([1-9]|1[0-2])$/.test(code) || code === "Space") return code;
	const key = String(event.key || "");
	return key.length === 1 ? key.toUpperCase() : null;
}

export function matches(event, spec, is_mac = IS_MAC) {
	if (!spec) return false;
	const meta = is_mac && spec.mod;
	const ctrl = spec.ctrl || (!is_mac && spec.mod);
	return (
		Boolean(event.metaKey) === meta &&
		Boolean(event.ctrlKey) === ctrl &&
		Boolean(event.altKey) === spec.alt &&
		Boolean(event.shiftKey) === spec.shift &&
		key_of(event) === spec.key
	);
}

// The shortcut a key press stands for, for recording a new one. null while only modifiers are
// down, or for a combination that would fire while typing (no Cmd/Ctrl/Alt and not an F key).
export function from_event(event, is_mac = IS_MAC) {
	const key = key_of(event);
	if (!key || !KEY.test(key)) return null;
	const mods = [];
	if (is_mac ? event.metaKey : event.ctrlKey) mods.push("Mod");
	if (is_mac && event.ctrlKey) mods.push("Ctrl");
	if (event.altKey) mods.push("Alt");
	if (event.shiftKey) mods.push("Shift");
	if (!mods.some((m) => m !== "Shift") && !key.startsWith("F")) return null;
	if (!is_mac && event.metaKey) return null; // the Windows key belongs to the system
	return [...mods, key].join("+");
}

// How it reads to the user: "⌘⇧P" on a Mac, "Ctrl+Shift+P" elsewhere; "" for none.
export function format(text, is_mac = IS_MAC) {
	const spec = parse(text);
	if (!spec) return "";
	const key = spec.key === "Space" ? (is_mac ? "␣" : "Space") : spec.key;
	if (is_mac) {
		// Apple's order: Control, Option, Shift, Command
		return `${spec.ctrl ? "⌃" : ""}${spec.alt ? "⌥" : ""}${spec.shift ? "⇧" : ""}${spec.mod ? "⌘" : ""}${key}`;
	}
	const mods = [spec.mod || spec.ctrl ? "Ctrl" : "", spec.alt ? "Alt" : "", spec.shift ? "Shift" : ""].filter(Boolean);
	return [...mods, key].join("+");
}
