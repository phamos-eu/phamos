// Run with `yarn test:spa` (vitest globals, see personal_frontend/vitest.config.js).
import { findMatches, stepIndex } from "./textSearch.js"

describe("page search", () => {
	it("finds every match, ignoring case and accents", () => {
		expect(findMatches("First acc issue, first ACC issue", "acc")).toEqual([6, 23])
		expect(findMatches("Café in Köln", "koln")).toEqual([8])
		expect(findMatches("Café", "cafe")).toEqual([0])
	})

	it("returns nothing for an empty query or text", () => {
		expect(findMatches("anything", "  ")).toEqual([])
		expect(findMatches("", "a")).toEqual([])
	})

	it("does not overlap matches", () => {
		expect(findMatches("aaaa", "aa")).toEqual([0, 2])
	})

	it("steps forward and back with wrap-around", () => {
		expect(stepIndex(-1, 3, 1)).toBe(0)
		expect(stepIndex(-1, 3, -1)).toBe(2)
		expect(stepIndex(2, 3, 1)).toBe(0)
		expect(stepIndex(0, 3, -1)).toBe(2)
		expect(stepIndex(0, 0, 1)).toBe(-1)
	})
})
