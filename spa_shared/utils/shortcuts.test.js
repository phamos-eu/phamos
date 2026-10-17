import { describe, expect, it } from "vitest"
import { insideOverlay, isCreateKey, isTypingTarget, listDirection, nextListIndex } from "./shortcuts.js"

describe("cockpit shortcuts", () => {
	it("leaves fields alone", () => {
		expect(isTypingTarget({ tagName: "INPUT" })).toBe(true)
		expect(isTypingTarget({ tagName: "TEXTAREA" })).toBe(true)
		expect(isTypingTarget({ tagName: "DIV", isContentEditable: true })).toBe(true)
		expect(isTypingTarget({ tagName: "BUTTON" })).toBe(false)
		expect(isTypingTarget(null)).toBe(false)
	})

	it("leaves dialogs and menus alone", () => {
		expect(insideOverlay({ closest: (sel) => (sel.includes("dialog") ? {} : null) })).toBe(true)
		expect(insideOverlay({ closest: () => null })).toBe(false)
		expect(insideOverlay(null)).toBe(false)
	})

	it("opens Create on Ctrl/Cmd+B only", () => {
		expect(isCreateKey({ ctrlKey: true, key: "b" })).toBe(true)
		expect(isCreateKey({ metaKey: true, key: "B" })).toBe(true)
		expect(isCreateKey({ ctrlKey: true, shiftKey: true, key: "b" })).toBe(false)
		expect(isCreateKey({ key: "b" })).toBe(false)
	})

	it("moves with j/k anywhere and with the arrows on a row", () => {
		expect(listDirection({ key: "j" }, false)).toBe(1)
		expect(listDirection({ key: "k" }, false)).toBe(-1)
		expect(listDirection({ key: "ArrowDown" }, false)).toBe(0) // the page keeps scrolling
		expect(listDirection({ key: "ArrowDown" }, true)).toBe(1)
		expect(listDirection({ key: "ArrowUp" }, true)).toBe(-1)
		expect(listDirection({ key: "j", ctrlKey: true }, true)).toBe(0)
		expect(listDirection({ key: "x" }, true)).toBe(0)
	})

	it("stops at the ends of a list", () => {
		expect(nextListIndex(-1, 5, 1)).toBe(0)
		expect(nextListIndex(-1, 5, -1)).toBe(4)
		expect(nextListIndex(2, 5, 1)).toBe(3)
		expect(nextListIndex(4, 5, 1)).toBe(4)
		expect(nextListIndex(0, 5, -1)).toBe(0)
		expect(nextListIndex(0, 0, 1)).toBe(-1)
	})
})
