import { describe, expect, it } from "vitest"
import { TAIL_H, bubble_path, jitter } from "./bubble.js"

describe("the speech bubble (PM, 2026-11-21)", () => {
	it("is one closed outline with its tail below the box", () => {
		const d = bubble_path(200, 40, 178)
		expect(d.startsWith("M")).toBe(true)
		expect(d.endsWith("Z")).toBe(true)
		expect(d).toContain(` ${40 - 0.5 + TAIL_H}`) // the tip reaches below the box
	})
	it("keeps the tail clear of the rounded corners, however small the box", () => {
		const tip_x = (d) => Number(d.match(/Q\S+ \S+ (\S+) /)[1])
		expect(tip_x(bubble_path(60, 30, 200))).toBeLessThanOrEqual(60 - 0.5 - 12 - 7)
		expect(tip_x(bubble_path(60, 30, -50))).toBeGreaterThanOrEqual(0.5 + 12 + 7)
	})
	it("leans its tail towards Phriend", () => {
		const tip = (d) => Number(d.match(/Q\S+ \S+ (\S+) /)[1])
		expect(tip(bubble_path(200, 40, 178, { lean: 7 }))).toBeCloseTo(tip(bubble_path(200, 40, 178)) + 7, 5)
		expect(tip(bubble_path(200, 40, 40, { lean: -7 }))).toBeCloseTo(tip(bubble_path(200, 40, 40)) - 7, 5)
	})
	it("jitters a little, never far", () => {
		for (const r of [0, 0.5, 0.9999]) {
			const j = jitter(() => r)
			expect(Math.abs(j.x)).toBeLessThanOrEqual(6)
			expect(j.y).toBeGreaterThanOrEqual(-4)
			expect(j.y).toBeLessThanOrEqual(2)
			expect(Math.abs(j.rot)).toBeLessThanOrEqual(2)
			expect(Math.abs(j.tail)).toBeLessThanOrEqual(6)
		}
		expect(jitter(() => 0)).not.toEqual(jitter(() => 1))
	})
})
