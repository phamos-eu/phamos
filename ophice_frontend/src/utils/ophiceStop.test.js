import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { STOP_DELAY, stopTimer } from "./ophiceStop.js"

describe("stopTimer (#2171)", () => {
	beforeEach(() => vi.useFakeTimers())
	afterEach(() => vi.useRealTimers())

	it("opens only after the pause, not at once", () => {
		const open = vi.fn()
		const stop = stopTimer(open, () => true)
		stop.stopped()
		expect(open).not.toHaveBeenCalled()
		vi.advanceTimersByTime(STOP_DELAY - 1)
		expect(open).not.toHaveBeenCalled()
		vi.advanceTimersByTime(1)
		expect(open).toHaveBeenCalledTimes(1)
	})

	it("a slight delay: under a second", () => {
		expect(STOP_DELAY).toBeGreaterThan(0)
		expect(STOP_DELAY).toBeLessThan(1000)
	})

	it("walking on within the pause opens nothing", () => {
		const open = vi.fn()
		const stop = stopTimer(open, () => true)
		stop.stopped()
		vi.advanceTimersByTime(STOP_DELAY / 2)
		stop.cancel()
		vi.advanceTimersByTime(STOP_DELAY * 2)
		expect(open).not.toHaveBeenCalled()
	})

	it("tapping past: every stop starts the pause again, one open at the end", () => {
		const open = vi.fn()
		const stop = stopTimer(open, () => true)
		for (let i = 0; i < 5; i++) {
			stop.stopped()
			vi.advanceTimersByTime(STOP_DELAY / 2)
		}
		expect(open).not.toHaveBeenCalled()
		vi.advanceTimersByTime(STOP_DELAY)
		expect(open).toHaveBeenCalledTimes(1)
	})

	it("opens nothing when I no longer stand still at the end of the pause", () => {
		const open = vi.fn()
		let standing = true
		const stop = stopTimer(open, () => standing)
		stop.stopped()
		standing = false
		vi.advanceTimersByTime(STOP_DELAY)
		expect(open).not.toHaveBeenCalled()
	})

	it("typing opens at once, only when a stop is pending", () => {
		const open = vi.fn()
		const stop = stopTimer(open, () => true)
		expect(stop.flush()).toBe(false)
		stop.stopped()
		expect(stop.pending).toBe(true)
		expect(stop.flush()).toBe(true)
		expect(open).toHaveBeenCalledTimes(1)
		expect(stop.pending).toBe(false)
		vi.advanceTimersByTime(STOP_DELAY)
		expect(open).toHaveBeenCalledTimes(1)
	})
})
