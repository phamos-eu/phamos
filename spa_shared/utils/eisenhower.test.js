// Run with `yarn test:spa` (vitest globals, see personal_frontend/vitest.config.js).
import { moveNeeds, quadrantForShortcut, quadrantOf, QUADRANTS } from "./eisenhower.js"

const UNTIL = "2026-10-16"

describe("Eisenhower quadrants", () => {
	it("derives the quadrant from the flag and the due date", () => {
		expect(quadrantOf({ important: true, date: "2026-10-01" }, UNTIL)).toBe("do")
		expect(quadrantOf({ important: true, date: "2026-10-16" }, UNTIL)).toBe("do")
		expect(quadrantOf({ important: true, date: "2026-10-19" }, UNTIL)).toBe("schedule")
		expect(quadrantOf({ important: false, date: "2026-10-14" }, UNTIL)).toBe("delegate")
		expect(quadrantOf({ important: false, date: null }, UNTIL)).toBe("eliminate")
	})

	it("maps the keys 1 to 4 in reading order", () => {
		expect(["1", "2", "3", "4"].map(quadrantForShortcut)).toEqual(QUADRANTS.map((q) => q.key))
		expect(quadrantForShortcut("5")).toBeNull()
	})

	it("asks for a later date only when a ToDo leaves urgent", () => {
		const dueToday = { important: true, date: "2026-10-14" }
		expect(moveNeeds(dueToday, "schedule", UNTIL)).toMatchObject({ laterDate: true, payoff: false })
		expect(moveNeeds(dueToday, "delegate", UNTIL)).toMatchObject({ laterDate: false, dueSoon: false })
	})

	it("asks the payoff question when a ToDo becomes important", () => {
		const someday = { important: false, date: null }
		expect(moveNeeds(someday, "do", UNTIL)).toMatchObject({ payoff: true, dueSoon: true, laterDate: false })
		expect(moveNeeds(someday, "eliminate", UNTIL).same).toBe(true)
	})
})
