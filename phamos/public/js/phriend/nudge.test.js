import { describe, expect, it } from "vitest"
import { after_click, after_nudge, fresh, is_due, parse } from "./nudge.js"

const DAY = 24 * 60 * 60 * 1000
const T0 = new Date(2026, 10, 19, 9, 0).getTime() // a Thursday morning, local time

describe("is_due", () => {
	it("nudges a user who never opened Phriend", () => {
		expect(is_due(fresh("a@x"), T0)).toBe(true)
	})

	it("waits the drawn idle time after Phriend was opened", () => {
		const state = after_click(fresh("a@x"), T0, () => 0.5) // 15 days
		expect(state.idle_days).toBe(15)
		expect(is_due(state, T0 + 1000)).toBe(false)
		expect(is_due(state, T0 + 15 * DAY - 1000)).toBe(false)
		expect(is_due(state, T0 + 15 * DAY)).toBe(true)
	})

	it("nudges once a day for the first three, then once a week", () => {
		let state = fresh("a@x")
		let now = T0
		for (let i = 0; i < 3; i++) {
			expect(is_due(state, now)).toBe(true)
			state = after_nudge(state, now)
			expect(is_due(state, now + 2 * 60 * 60 * 1000)).toBe(false) // same day
			now += DAY
		}
		expect(state.nudges).toBe(3)
		expect(is_due(state, now)).toBe(false) // the day after the third
		expect(is_due(state, T0 + 2 * DAY + 7 * DAY - 1000)).toBe(false)
		expect(is_due(state, T0 + 2 * DAY + 7 * DAY)).toBe(true)
	})

	it("starts over after Phriend is opened", () => {
		let state = after_nudge(after_nudge(after_nudge(after_nudge(fresh("a@x"), T0), T0 + DAY), T0 + 2 * DAY), T0 + 9 * DAY)
		state = after_click(state, T0 + 10 * DAY, () => 0)
		expect(state).toMatchObject({ nudges: 0, nudged_at: null, idle_days: 10 })
		expect(is_due(state, T0 + 19 * DAY)).toBe(false)
		expect(is_due(state, T0 + 20 * DAY)).toBe(true)
	})

	it("does not nudge again when the clock went back", () => {
		const state = after_nudge(fresh("a@x"), T0)
		expect(is_due(state, T0 - DAY)).toBe(false)
	})
})

describe("after_click", () => {
	it("draws an idle time from 10 to 20 days", () => {
		expect(after_click(fresh(), T0, () => 0).idle_days).toBe(10)
		expect(after_click(fresh(), T0, () => 0.999999).idle_days).toBe(20)
		expect(after_click(fresh(), T0, () => 1).idle_days).toBe(20)
		for (let i = 0; i < 200; i++) {
			const days = after_click(fresh(), T0).idle_days
			expect(days).toBeGreaterThanOrEqual(10)
			expect(days).toBeLessThanOrEqual(20)
		}
	})
})

describe("parse", () => {
	it("reads back what was stored", () => {
		const state = after_nudge(after_click(fresh("a@x"), T0, () => 0.3), T0 + 20 * DAY)
		expect(parse(JSON.stringify(state), "a@x")).toEqual(state)
	})

	it("starts fresh for a broken value", () => {
		for (const text of [null, "", "{", "42", "[]", '"x"'])
			expect(parse(text, "a@x")).toEqual(fresh("a@x"))
	})

	it("starts fresh for another user's value", () => {
		const state = after_click(fresh("a@x"), T0)
		expect(parse(JSON.stringify(state), "b@x")).toEqual(fresh("b@x"))
	})

	it("repairs values out of range", () => {
		const text = JSON.stringify({ user: "a@x", clicked_at: T0, idle_days: 400, nudged_at: "soon", nudges: -2 })
		expect(parse(text, "a@x")).toEqual({ user: "a@x", clicked_at: T0, idle_days: 10, nudged_at: null, nudges: 0 })
	})
})
