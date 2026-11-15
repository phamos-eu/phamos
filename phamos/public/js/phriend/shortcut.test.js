import { describe, expect, it } from "vitest"
import { format, from_event, key_of, matches, parse } from "./shortcut.js"

const press = (code, mods = {}) => ({ code, key: code.replace(/^(Key|Digit)/, "").toLowerCase(), ...mods })

describe("parse", () => {
	it("reads the notation phriend/shortcut.py writes", () => {
		expect(parse("Mod+P")).toEqual({ mod: true, ctrl: false, alt: false, shift: false, key: "P" })
		expect(parse("Alt+Shift+P")).toMatchObject({ alt: true, shift: true, key: "P" })
		expect(parse("Ctrl+F5")).toMatchObject({ ctrl: true, key: "F5" })
	})
	it("returns null for none or nonsense", () => {
		expect(parse("")).toBeNull()
		expect(parse(null)).toBeNull()
		expect(parse("Mod+P+Q")).toBeNull()
		expect(parse("Hyper+P")).toBeNull()
	})
})

describe("matches", () => {
	const modP = parse("Mod+P")
	it("Mod is Cmd on a Mac and Ctrl elsewhere", () => {
		expect(matches(press("KeyP", { metaKey: true }), modP, true)).toBe(true)
		expect(matches(press("KeyP", { ctrlKey: true }), modP, true)).toBe(false)
		expect(matches(press("KeyP", { ctrlKey: true }), modP, false)).toBe(true)
		expect(matches(press("KeyP", { metaKey: true }), modP, false)).toBe(false)
	})
	it("needs exactly the modifiers given", () => {
		expect(matches(press("KeyP", { metaKey: true, shiftKey: true }), modP, true)).toBe(false)
		expect(matches(press("KeyO", { metaKey: true }), modP, true)).toBe(false)
	})
	it("goes by key position, so Option on a Mac doesn't matter", () => {
		const altShiftP = parse("Alt+Shift+P")
		expect(matches({ code: "KeyP", key: "∏", altKey: true, shiftKey: true }, altShiftP, true)).toBe(true)
		expect(key_of({ code: "Digit5", key: "%" })).toBe("5")
	})
})

describe("from_event (recording a new shortcut)", () => {
	it("writes what was pressed in the shared notation", () => {
		expect(from_event(press("KeyK", { metaKey: true, shiftKey: true }), true)).toBe("Mod+Shift+K")
		expect(from_event(press("KeyK", { ctrlKey: true, altKey: true }), false)).toBe("Mod+Alt+K")
		expect(from_event(press("KeyK", { ctrlKey: true }), true)).toBe("Ctrl+K")
		expect(from_event(press("F2"), false)).toBe("F2")
	})
	it("refuses what would fire while typing, or only modifiers", () => {
		expect(from_event(press("KeyK"), true)).toBeNull()
		expect(from_event(press("KeyK", { shiftKey: true }), true)).toBeNull()
		expect(from_event({ code: "ShiftLeft", key: "Shift", shiftKey: true }, true)).toBeNull()
	})
})

describe("format", () => {
	it("shows Mac symbols on a Mac and words elsewhere", () => {
		expect(format("Mod+P", true)).toBe("⌘P")
		expect(format("Alt+Shift+P", true)).toBe("⌥⇧P")
		expect(format("Mod+P", false)).toBe("Ctrl+P")
		expect(format("Mod+Alt+Shift+P", false)).toBe("Ctrl+Alt+Shift+P")
		expect(format("", true)).toBe("")
	})
})
