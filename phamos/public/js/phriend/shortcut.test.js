import { describe, expect, it } from "vitest"
import rules from "./shortcut_rules.json"
import { format, from_event, key_of, matches, parse, problem } from "./shortcut.js"

const press = (code, mods = {}) => ({ code, key: code.replace(/^(Key|Digit)/, "").toLowerCase(), ...mods })

describe("parse", () => {
	it("reads the notation phriend/shortcut.py writes", () => {
		expect(parse("Mod+P")).toEqual({ mod: true, ctrl: false, alt: false, shift: false, key: "P" })
		expect(parse("Mod+Shift+K")).toMatchObject({ mod: true, shift: true, key: "K" })
		expect(parse("Ctrl+F5")).toMatchObject({ ctrl: true, key: "F5" })
	})
	it("returns null for none or nonsense", () => {
		expect(parse("")).toBeNull()
		expect(parse(null)).toBeNull()
		expect(parse("Mod+P+Q")).toBeNull()
		expect(parse("Hyper+P")).toBeNull()
	})
})

describe("problem (the rules both sides share)", () => {
	it("accepts the allowed examples and refuses the refused ones", () => {
		for (const text of rules.examples.allowed) expect([text, problem(text)]).toEqual([text, null])
		for (const text of rules.examples.refused) expect([text, problem(text)]).not.toEqual([text, null])
	})
	it("says why", () => {
		expect(problem("Shift+F")).toBe("modifier") // the letter F, not an F key
		expect(problem("F5")).toBe("modifier")
		expect(problem("Alt+L")).toBe("modifier")
		expect(problem("Mod+Alt+P")).toBe("alt") // AltGr on Windows, Option on a Mac
		expect(problem("Mod+C")).toBe("reserved")
		expect(problem("Mod+Shift+B")).toBe("reserved") // the bookmarks bar
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
	it("goes by the letter on the key, so a German Z is Z (it sits where Y is on English keyboards)", () => {
		const german_z = { code: "KeyY", key: "z", metaKey: true }
		expect(key_of(german_z)).toBe("Z")
		expect(matches(german_z, parse("Mod+Y"), true)).toBe(false)
	})
	it("falls back to the key's position when Option changes the character", () => {
		expect(key_of({ code: "KeyP", key: "∏", altKey: true, shiftKey: true })).toBe("P")
		expect(key_of({ code: "Digit5", key: "%", shiftKey: true })).toBe("5")
	})
})

describe("from_event (recording a new shortcut)", () => {
	it("writes what was pressed in the shared notation", () => {
		expect(from_event(press("KeyK", { metaKey: true, shiftKey: true }), true)).toBe("Mod+Shift+K")
		expect(from_event(press("KeyK", { ctrlKey: true, altKey: true }), false)).toBe("Mod+Alt+K")
		expect(from_event(press("KeyK", { ctrlKey: true }), true)).toBe("Ctrl+K")
		expect(from_event(press("KeyF"), true)).toBe("F")
	})
	it("returns null while only modifiers are down, or for the Windows key", () => {
		expect(from_event({ code: "ShiftLeft", key: "Shift", shiftKey: true }, true)).toBeNull()
		expect(from_event(press("KeyK", { metaKey: true }), false)).toBeNull()
	})
	it("what it records goes through problem()", () => {
		expect(problem(from_event(press("KeyF"), true))).toBe("modifier")
		expect(problem(from_event(press("KeyF", { shiftKey: true }), true))).toBe("modifier")
		expect(problem(from_event(press("KeyK", { metaKey: true }), true))).toBeNull()
	})
})

describe("format", () => {
	it("shows Mac symbols on a Mac and words elsewhere", () => {
		expect(format("Mod+P", true)).toBe("⌘P")
		expect(format("Mod+Shift+K", true)).toBe("⇧⌘K")
		expect(format("Mod+P", false)).toBe("Ctrl+P")
		expect(format("Mod+Shift+K", false)).toBe("Ctrl+Shift+K")
		expect(format("", true)).toBe("")
	})
})
