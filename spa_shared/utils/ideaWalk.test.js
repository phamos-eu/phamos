import { describe, expect, it } from "vitest"
import { createWalkQueue, walkStep } from "./ideaWalk.js"

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
		expect(walkStep(null, "x")).toEqual({ next: null, position: 0, total: 0 })
	})
})

describe("createWalkQueue", () => {
	it("keeps the first order while the list reorders", async () => {
		let order = ["a", "b", "c"]
		let loads = 0
		const queue = createWalkQueue(async () => {
			loads += 1
			return order
		})
		expect(await queue.step("a")).toEqual({ next: "b", position: 1, total: 3 })
		order = ["c", "b", "a"]
		expect(await queue.step("b")).toEqual({ next: "c", position: 2, total: 3 })
		expect(loads).toBe(1)
	})

	it("takes a fresh order after a reset", async () => {
		let order = ["a", "b"]
		const queue = createWalkQueue(async () => order)
		await queue.step("a")
		queue.reset()
		order = ["b", "a", "c"]
		expect(await queue.step("a")).toEqual({ next: "c", position: 2, total: 3 })
	})

	it("does not keep an order that arrives after a reset", async () => {
		let release
		let order = ["a", "b"]
		const queue = createWalkQueue(() => new Promise((resolve) => (release = () => resolve(order))))
		const pending = queue.step("a")
		queue.reset()
		release()
		await pending
		order = ["b", "a"]
		const fresh = queue.step("a")
		release()
		expect(await fresh).toEqual({ next: null, position: 2, total: 2 })
	})
})
