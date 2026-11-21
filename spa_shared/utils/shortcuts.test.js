import { describe, expect, it } from "vitest"
import {
	dialogOpen,
	dialogPrimaryAction,
	insideOverlay,
	isCreateKey,
	isSaveKey,
	isTypingTarget,
	listDirection,
	nextListIndex,
	topDialog,
} from "./shortcuts.js"

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
		// frappe-ui popovers have no role; they live in #frappeui-popper-root.
		expect(insideOverlay({ closest: (sel) => (sel.includes("#frappeui-popper-root") ? {} : null) })).toBe(true)
		expect(dialogOpen({ querySelector: () => ({}) })).toBe(true)
		expect(dialogOpen({ querySelector: () => null })).toBe(false)
		expect(dialogOpen(null)).toBe(false)
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

	it("saves on Ctrl/Cmd+S only", () => {
		expect(isSaveKey({ metaKey: true, key: "s" })).toBe(true)
		expect(isSaveKey({ ctrlKey: true, key: "S" })).toBe(true)
		expect(isSaveKey({ metaKey: true, shiftKey: true, key: "s" })).toBe(false)
		expect(isSaveKey({ ctrlKey: true, altKey: true, key: "s" })).toBe(false)
		expect(isSaveKey({ key: "s" })).toBe(false)
	})

	it("takes the dialog on top", () => {
		const first = {}
		const second = {}
		const root = (sel) => ({ querySelectorAll: (s) => (s === sel ? [first, second] : []) })
		expect(topDialog(root('[role="dialog"][id^="headlessui-dialog-"]'))).toBe(second)
		// Full-page surfaces with role="dialog" only (idea writing mode) are not dialogs here.
		expect(topDialog(root('[role="dialog"]'))).toBe(null)
		expect(topDialog({ querySelectorAll: () => [] })).toBe(null)
		expect(topDialog(null)).toBe(null)
	})

	describe("dialog primary action", () => {
		const SOLID = "text-ink-white bg-surface-gray-7"
		const RED = "text-ink-white bg-surface-red-5"
		const SUBTLE = "text-ink-gray-8 bg-surface-gray-2"
		// What frappe-ui renders for a disabled or loading button, whatever its variant.
		const DISABLED = "text-ink-gray-4 bg-surface-gray-2"
		const button = (classes, { disabled = false, marked = false } = {}) => ({
			tagName: "BUTTON",
			disabled,
			marked,
			classList: { contains: (name) => classes.split(" ").includes(name) },
		})
		const dialog = (buttons = [], forms = []) => ({
			querySelector: (sel) => (sel === "[data-primary-action]" ? buttons.find((b) => b.marked) || null : null),
			querySelectorAll: (sel) => (sel === "button" ? buttons : sel === "form" ? forms : []),
		})

		it("clicks the one solid button", () => {
			const ok = button(SOLID)
			expect(dialogPrimaryAction(dialog([button(SUBTLE), ok]))).toBe(ok)
		})

		it("runs nothing while the button is disabled or loading, and never submits its form", () => {
			const form = { tagName: "FORM" }
			expect(dialogPrimaryAction(dialog([button(DISABLED, { disabled: true })], [form]))).toBe(null)
			expect(dialogPrimaryAction(dialog([button(SUBTLE), button(DISABLED, { disabled: true })]))).toBe(null)
		})

		it("never runs a red button", () => {
			expect(dialogPrimaryAction(dialog([button(RED)]))).toBe(null)
			expect(dialogPrimaryAction(dialog([button(RED)], [{ tagName: "FORM" }]))).toBe(null)
			const ok = button(SOLID)
			expect(dialogPrimaryAction(dialog([button(RED), ok]))).toBe(ok)
		})

		it("does not guess between two solid buttons", () => {
			expect(dialogPrimaryAction(dialog([button(SOLID), button(SOLID)]))).toBe(null)
		})

		it("prefers a marked button", () => {
			const marked = button(SUBTLE, { marked: true })
			expect(dialogPrimaryAction(dialog([button(SOLID), marked]))).toBe(marked)
			expect(dialogPrimaryAction(dialog([button(SOLID), button(SUBTLE, { marked: true, disabled: true })]))).toBe(null)
		})

		it("submits the one form when there is no solid button", () => {
			const form = { tagName: "FORM" }
			expect(dialogPrimaryAction(dialog([button(SUBTLE)], [form]))).toBe(form)
			expect(dialogPrimaryAction(dialog([], [form, { tagName: "FORM" }]))).toBe(null)
		})

		it("does nothing in an info-only dialog", () => {
			expect(dialogPrimaryAction(dialog([button(SUBTLE)]))).toBe(null)
			expect(dialogPrimaryAction(null)).toBe(null)
		})
	})
})
