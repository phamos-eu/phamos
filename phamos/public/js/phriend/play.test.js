import { describe, expect, it } from "vitest"
import { readFileSync } from "node:fs"
import { GESTURES } from "./ball.js"
import { COOLDOWN_MS, FAST_DRAG, HOVER_MOVES, IDLE_MOVES, MOVES, cooled_down, pick, top_speed } from "./play.js"

const ball_source = readFileSync(new URL("./ball.js", import.meta.url), "utf8")

describe("easter eggs (#2013)", () => {
	it("has CSS for every move and a real emoji where it shows one", () => {
		for (const [name, move] of Object.entries(MOVES)) {
			expect(ball_source, name).toContain(`.ball.play-${name} `)
			if (move.emoji) expect(GESTURES[move.emoji], name).toBeTruthy()
		}
		for (const name of [...HOVER_MOVES, ...IDLE_MOVES]) expect(MOVES[name], name).toBeTruthy()
	})
	it("never plays the same move twice in a row", () => {
		for (const r of [0, 0.4, 0.9999]) expect(pick(HOVER_MOVES, "spin", () => r)).not.toBe("spin")
		expect(pick(["dizzy"], "dizzy")).toBe("dizzy")
	})
	it("waits a few minutes before the same trigger plays again", () => {
		expect(cooled_down(undefined, 1000)).toBe(true)
		expect(cooled_down(1000, 1000 + COOLDOWN_MS - 1)).toBe(false)
		expect(cooled_down(1000, 1000 + COOLDOWN_MS)).toBe(true)
	})
	it("tells a fast shake from a calm drag", () => {
		const calm = [{ x: 0, y: 0, t: 0 }, { x: 10, y: 0, t: 16 }, { x: 20, y: 0, t: 32 }, { x: 30, y: 0, t: 48 }]
		const shake = [{ x: 0, y: 0, t: 0 }, { x: 60, y: 0, t: 16 }, { x: 0, y: 0, t: 32 }, { x: 60, y: 0, t: 48 }]
		expect(top_speed(calm)).toBeLessThan(FAST_DRAG)
		expect(top_speed(shake)).toBeGreaterThanOrEqual(FAST_DRAG)
		expect(top_speed([])).toBe(0)
	})
	it("isn't fooled by two events a millisecond apart (AI review of !1285)", () => {
		// a calm drag at 0.5 px/ms with one pair of events 1 ms and 3 px apart
		const drag = [{ x: 0, y: 0, t: 0 }, { x: 8, y: 0, t: 16 }, { x: 11, y: 0, t: 17 }, { x: 16, y: 0, t: 32 }, { x: 24, y: 0, t: 48 }]
		expect(top_speed(drag)).toBeLessThan(FAST_DRAG)
		// and a stretch shorter than the window isn't measured at all
		expect(top_speed([{ x: 0, y: 0, t: 0 }, { x: 5, y: 0, t: 1 }])).toBe(0)
	})
	it("looks nothing like sleeping (PM, 2026-11-21)", () => {
		for (const name of Object.keys(MOVES)) expect(name).not.toMatch(/sleep|yawn|stretch|doze/)
	})
})
