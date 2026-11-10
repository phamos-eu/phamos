import { describe, expect, it } from "vitest"
import { walkStep } from "./ideaWalk.js"

describe("walkStep", () => {
	it("gives the next idea and the position", () => {
		expect(walkStep(["a", "b", "c"], "a")).toEqual({ next: "b", position: 1, total: 3 })
		expect(walkStep(["a", "b", "c"], "b")).toEqual({ next: "c", position: 2, total: 3 })
	})

	it("has no next idea after the last one", () => {
		expect(walkStep(["a", "b", "c"], "c")).toEqual({ next: null, position: 3, total: 3 })
	})

	it("has no position for an idea outside the walk", () => {
		expect(walkStep(["a", "b"], "x")).toEqual({ next: null, position: 0, total: 2 })
		expect(walkStep([], "x")).toEqual({ next: null, position: 0, total: 0 })
	})
})
