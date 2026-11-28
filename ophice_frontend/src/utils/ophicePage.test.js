import { describe, expect, it } from "vitest"
import { isOwnPage } from "./ophicePage.js"

const ORIGIN = "https://erp.example.com"

describe("isOwnPage", () => {
	it("accepts cockpit pages of this site", () => {
		expect(isOwnPage("/personal-cockpit/todos/plan", ORIGIN)).toBe(true)
		expect(isOwnPage("/sales-cockpit/leads?status=Open#top", ORIGIN)).toBe(true)
	})

	it("refuses other sites in every spelling", () => {
		for (const page of ["//evil.com/x", "/\\evil.com/x", "///evil.com", "https://evil.com", "javascript:alert(1)", "", "/"]) {
			expect(isOwnPage(page, ORIGIN)).toBe(false)
		}
	})
})
