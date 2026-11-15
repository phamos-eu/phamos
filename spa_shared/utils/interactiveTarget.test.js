import { isInteractiveTarget } from "./interactiveTarget.js"

// Stand-ins for DOM elements: matches() by tag name, a parent chain.
function el(tag, parent = null) {
	return { tag, parentElement: parent, matches: (selector) => selector.split(",").map((s) => s.trim()).includes(tag) }
}

describe("isInteractiveTarget", () => {
	const card = el("div[role=button]")
	const body = el("div", card)
	const field = el("input", body)
	const textInField = el("span", el("button", body))

	it("is true for a field or something inside a button", () => {
		expect(isInteractiveTarget(field, body)).toBe(true)
		expect(isInteractiveTarget(textInField, body)).toBe(true)
	})

	it("is false for the card's free area, and stops at the boundary", () => {
		expect(isInteractiveTarget(body, body)).toBe(false)
		expect(isInteractiveTarget(el("p", body), body)).toBe(false)
		// the card around is role=button, but it is outside the boundary
		expect(isInteractiveTarget(body, body, "div[role=button]")).toBe(false)
	})
})
