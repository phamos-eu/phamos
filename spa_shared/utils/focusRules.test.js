// Run with `yarn test:spa` (vitest globals, see personal_frontend/vitest.config.js).
import { activeItem, breakOutWait, formatClock, secondsBetween, sessionClock } from "./focusRules.js"

const session = {
	started_at: "2026-10-15 09:00:00",
	server_now: "2026-10-15 09:10:00",
	planned_minutes: 25,
	planned_end: "2026-10-15 09:25:00",
	free_exit_seconds: 60,
	break_out_wait_seconds: 20,
	items: [
		{ todo: "a", done: true, parked: false, current: false },
		{ todo: "b", done: false, parked: true, current: false },
		{ todo: "c", done: false, parked: false, current: false },
	],
}

describe("focus clock", () => {
	it("counts down from the server's view of now", () => {
		expect(secondsBetween(session.started_at, session.server_now)).toBe(600)
		expect(sessionClock(session, 30)).toEqual({ mode: "timer", elapsed: 630, remaining: 870, overtime: false })
		expect(sessionClock(session, 1000)).toMatchObject({ remaining: 0, overtime: true })
	})

	it("runs as a stopwatch without planned minutes", () => {
		expect(sessionClock({ ...session, planned_minutes: 0, planned_end: null }, 5)).toMatchObject({
			mode: "stopwatch",
			elapsed: 605,
			remaining: null,
		})
	})

	it("formats minutes and hours", () => {
		expect(formatClock(65)).toBe("1:05")
		expect(formatClock(3725)).toBe("1:02:05")
		expect(formatClock(-3)).toBe("0:00")
	})
})

describe("focus rules", () => {
	it("lets you leave freely in the first minute, then waits", () => {
		expect(breakOutWait(59, session)).toBe(0)
		expect(breakOutWait(60, session)).toBe(20)
	})

	it("shows the current ToDo, else the next open one", () => {
		expect(activeItem(session).todo).toBe("c")
		expect(activeItem({ items: [{ todo: "x", current: true }] }).todo).toBe("x")
		expect(activeItem({ items: [] })).toBeNull()
	})
})
