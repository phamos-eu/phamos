import { describe, expect, it } from "vitest"
import { progress, stepIndex, stepState } from "./stageSteps.js"

const STEPS = ["Seed", "Sprout", "Seedling", "Young plant", "Growing", "Mature", "Harvest"].map((v) => ({
	value: v,
	label: v,
}))

describe("stageSteps", () => {
	it("finds the current step", () => {
		expect(stepIndex(STEPS, "Growing")).toBe(4)
		expect(stepIndex(STEPS, "Compost")).toBe(-1)
		expect(stepIndex(null, "Seed")).toBe(-1)
	})

	it("marks steps before the current one as done", () => {
		const current = stepIndex(STEPS, "Growing")
		expect(STEPS.map((_, i) => stepState(i, current))).toEqual([
			"done",
			"done",
			"done",
			"done",
			"current",
			"upcoming",
			"upcoming",
		])
	})

	it("shows nothing done for a value off the path", () => {
		expect(STEPS.map((_, i) => stepState(i, -1)).every((s) => s === "upcoming")).toBe(true)
	})

	it("gives the step numbers for the tooltip", () => {
		expect(progress(STEPS, "Growing")).toEqual({ label: "Growing", step: 5, total: 7 })
		expect(progress(STEPS, "Compost")).toBeNull()
	})
})
