// Phriend's keyboard shortcut (#1903), in the notation phamos/phriend/shortcut.py keeps:
// modifiers then one key, e.g. "Mod+P" or "Mod+Shift+K". "Mod" is Cmd on a Mac, Ctrl elsewhere.
// What may not be a shortcut is in shortcut_rules.json, read by both sides.
// Pure functions, tested in shortcut.test.js.

import rules from "./shortcut_rules.json";

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

// The key of a keyboard event: the letter or digit printed on it (event.key), so Z is Z on a
// German keyboard too, where it sits where Y is on an English one. Without a printable letter
// (F keys, Space, or Option changing the character) by its position (event.code).
export function key_of(event) {
	const key = String(event.key || "");
	if (!event.altKey && /^[a-z0-9]$/i.test(key)) return key.toUpperCase();
	const code = event.code || "";
	if (/^Key[A-Z]$/.test(code)) return code.slice(3);
	if (/^Digit[0-9]$/.test(code)) return code.slice(5);
	if (/^F([1-9]|1[0-2])$/.test(code) || code === "Space") return code;
	return null;
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

// Why a shortcut can't be used: "modifier", "alt", "reserved", or null when it's fine.
// The same rules as problem() in phamos/phriend/shortcut.py.
export function problem(text) {
	const spec = parse(text);
	if (!spec || !(spec.mod || spec.ctrl)) return "modifier";
	if (spec.alt) return "alt";
	if (rules.refused[spec.shift ? "shift" : "plain"].includes(spec.key)) return "reserved";
	return null;
}

// The shortcut a key press stands for, for recording a new one ("Mod+Shift+K"); null while only
// modifiers are down. Whether it may be used is problem()'s question.
export function from_event(event, is_mac = IS_MAC) {
	const key = key_of(event);
	if (!key || !KEY.test(key)) return null;
	const mods = [];
	if (is_mac ? event.metaKey : event.ctrlKey) mods.push("Mod");
	if (is_mac && event.ctrlKey) mods.push("Ctrl");
	if (!is_mac && event.metaKey) return null; // the Windows key belongs to the system
	if (event.altKey) mods.push("Alt");
	if (event.shiftKey) mods.push("Shift");
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
