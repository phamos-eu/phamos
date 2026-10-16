// Run with `yarn test:spa` (vitest globals, see personal_frontend/vitest.config.js).
import { budgetText, countdown, formatClock, formatMinutes, isOverBudget, liveBreak, liveElapsed, minutesToSeconds } from "./timerClock.js"

const running = { state: "running", elapsed_seconds: 600, expected_time: 3600 }

describe("timer clock", () => {
	it("advances only while running", () => {
		expect(liveElapsed(running, 30.7)).toBe(630)
		expect(liveElapsed({ ...running, state: "paused" }, 30)).toBe(600)
		expect(liveElapsed(null)).toBe(0)
	})

	it("counts the break from the server's clock", () => {
		const paused = { state: "paused", break_from: "2026-10-16 10:00:00" }
		expect(liveBreak(paused, "2026-10-16 10:05:00", 10)).toBe(310)
		expect(liveBreak({ ...paused, state: "running" }, "2026-10-16 10:05:00")).toBe(0)
	})

	it("formats the clock with hours", () => {
		expect(formatClock(0)).toBe("00:00:00")
		expect(formatClock(2533)).toBe("00:42:13")
		expect(formatClock(36061)).toBe("10:01:01")
	})

	it("says how much of the expected time is left or over", () => {
		expect(budgetText(running, 600)).toBe("50 min left")
		expect(budgetText(running, 4080)).toBe("8 min over")
		expect(budgetText({ expected_time: 0 }, 100)).toBe("")
		expect(isOverBudget(running, 3601)).toBe(true)
		expect(formatMinutes(5400)).toBe("1 h 30 min")
		expect(formatMinutes(20)).toBe("under a minute")
	})

	it("parses expected minutes with a minimum", () => {
		expect(minutesToSeconds(60)).toBe(3600)
		expect(minutesToSeconds("45")).toBe(2700)
		expect(minutesToSeconds(10)).toBeNull()
		expect(minutesToSeconds(5, 1)).toBe(300)
		expect(minutesToSeconds("abc")).toBeNull()
	})

	it("counts down from the target and then shows the overtime", () => {
		expect(countdown(3600, 600)).toEqual({ text: "00:50:00", over: false })
		expect(countdown(3600, 3600)).toEqual({ text: "00:00:00", over: false })
		expect(countdown(3600, 3912)).toEqual({ text: "+00:05:12", over: true })
		expect(countdown(0, 75)).toEqual({ text: "00:01:15", over: false })
	})
})
