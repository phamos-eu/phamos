import { describe, expect, it } from "vitest"
import { stepBlocked } from "./ophiceStep.js"

const MIN = 0.8

describe("stepBlocked", () => {
	it("blocks a step into another chip", () => {
		const others = [{ x: 5, y: 5 }]
		expect(stepBlocked(others, { x: 3.5, y: 5 }, { x: 4.3, y: 5 }, MIN)).toBe(true)
	})

	it("lets a free step through", () => {
		const others = [{ x: 5, y: 5 }]
		expect(stepBlocked(others, { x: 1, y: 5 }, { x: 1.1, y: 5 }, MIN)).toBe(false)
	})

	// #2160: on top of each other, every small step still ends inside MIN; it must not block.
	it("lets a chip on top of another walk away in any direction", () => {
		const others = [{ x: 5, y: 5 }]
		const from = { x: 5, y: 5 }
		for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1], [0.7, 0.7]]) {
			expect(stepBlocked(others, from, { x: 5 + dx * 0.05, y: 5 + dy * 0.05 }, MIN)).toBe(false)
		}
	})

	it("lets an overlapping chip step away but not closer", () => {
		const others = [{ x: 5, y: 5 }]
		const from = { x: 5.3, y: 5 }
		expect(stepBlocked(others, from, { x: 5.35, y: 5 }, MIN)).toBe(false)
		expect(stepBlocked(others, from, { x: 5.25, y: 5 }, MIN)).toBe(true)
	})

	it("still blocks walking into a second chip while leaving the first", () => {
		const others = [{ x: 5, y: 5 }, { x: 5.8, y: 5 }]
		expect(stepBlocked(others, { x: 5, y: 5 }, { x: 5.1, y: 5 }, MIN)).toBe(true)
	})

	it("ignores offline chips", () => {
		const others = [{ x: 5, y: 5, offline: true }]
		expect(stepBlocked(others, { x: 4, y: 5 }, { x: 5, y: 5 }, MIN)).toBe(false)
	})
})
