import { describe, expect, it } from "vitest"
import { picks_html, question_text } from "./rating.js"

const __ = (text, args = []) => text.replace(/\{(\d)\}/g, (_, i) => args[i])

describe("rating a fix (#2014)", () => {
	it("asks bugs whether they are fixed and improvements how they are liked, now and later", () => {
		expect(question_text(__, { kind: "Thumbs", round: "First impression", title: "Totals" })).toBe("“Totals” is live. Did it fix it?")
		expect(question_text(__, { kind: "Thumbs", round: "Battle tested", title: "Totals" })).toContain("Still fixed?")
		expect(question_text(__, { kind: "Stars", round: "First impression", title: "Search" })).toContain("How do you like it?")
		expect(question_text(__, { kind: "Stars", round: "Battle tested", title: "Search" })).toContain("How do you like it now?")
	})
	it("escapes the report's title", () => {
		expect(question_text(__, { kind: "Thumbs", title: "<img src=x onerror=alert(1)>" })).not.toContain("<img")
	})
	it("offers thumbs for bugs and five stars for improvements", () => {
		expect((picks_html(__, "Thumbs").match(/class="pick"/g) || []).length).toBe(2)
		expect(picks_html(__, "Thumbs")).toContain('data-r="-1"')
		expect((picks_html(__, "Stars").match(/class="pick"/g) || []).length).toBe(5)
	})
})
