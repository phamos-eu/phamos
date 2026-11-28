import { describe, expect, it } from "vitest"
import { has_budget, is_editable, is_typing, local_day } from "./voice.js"

describe("one voice (#2011)", () => {
	it("counts the user's own calendar day", () => {
		expect(local_day(new Date(2026, 10, 21, 23, 59).getTime())).toBe("2026-11-21")
		expect(local_day(new Date(2026, 0, 2, 0, 1).getTime())).toBe("2026-01-02")
	})
	it("has a bubble left until today's are used; a new day starts again", () => {
		expect(has_budget({ day: "2026-11-21", used: 0, limit: 1 }, "2026-11-21")).toBe(true)
		expect(has_budget({ day: "2026-11-21", used: 1, limit: 1 }, "2026-11-21")).toBe(false)
		expect(has_budget({ day: "2026-11-20", used: 1, limit: 1 }, "2026-11-21")).toBe(true)
		expect(has_budget({ day: "", used: 0, limit: 0 }, "2026-11-21")).toBe(false)
		expect(has_budget(null, "2026-11-21")).toBe(false)
	})
	it("knows a text field from a button", () => {
		expect(is_editable({ tagName: "TEXTAREA" })).toBe(true)
		expect(is_editable({ tagName: "INPUT", type: "text" })).toBe(true)
		expect(is_editable({ tagName: "INPUT", type: "checkbox" })).toBe(false)
		expect(is_editable({ tagName: "DIV", isContentEditable: true })).toBe(true)
		expect(is_editable({ tagName: "BUTTON" })).toBe(false)
		expect(is_editable(null)).toBe(false)
	})
	it("waits while someone types or just typed", () => {
		const now = 100_000
		expect(is_typing({ tagName: "INPUT", type: "text" }, 0, now)).toBe(true)
		expect(is_typing({ tagName: "BODY" }, now - 1000, now)).toBe(true)
		expect(is_typing({ tagName: "BODY" }, now - 10_000, now)).toBe(false)
	})
})
