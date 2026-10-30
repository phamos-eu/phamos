// Run with `yarn test:spa` (vitest globals, see personal_frontend/vitest.config.js).
import { newTaskDefaults, newTaskErrors, withStartDate } from "./newTaskForm.js"

const options = {
	task_priorities: ["Low", "Medium", "High", "Urgent"],
	sales_standard_project: "PROJ-SALES",
}

describe("new task form", () => {
	it("starts with today, me, 1 hour, Medium and the cockpit's project", () => {
		const form = newTaskDefaults({
			subject: "  Prepare offer ",
			today: "2026-11-02",
			user: "me@example.com",
			options,
			projectField: "sales_standard_project",
		})
		expect(form).toEqual({
			subject: "Prepare offer",
			exp_start_date: "2026-11-02",
			exp_end_date: "2026-11-02",
			custom_task_owner: "me@example.com",
			expected_time: 1,
			priority: "Medium",
			project: "PROJ-SALES",
			task_type: "",
			description: "",
		})
		expect(newTaskErrors(form)).toEqual([])
	})

	it("has no project preset in the personal cockpit", () => {
		const form = newTaskDefaults({ today: "2026-11-02", user: "me@example.com", options })
		expect(form.project).toBe("")
		expect(form.subject).toBe("")
	})

	it("moves the end along when the start goes past it", () => {
		const form = { exp_start_date: "2026-11-02", exp_end_date: "2026-11-04" }
		expect(withStartDate(form, "2026-11-06").exp_end_date).toBe("2026-11-06")
		expect(withStartDate(form, "2026-11-03").exp_end_date).toBe("2026-11-04")
	})

	it("names each missing required field", () => {
		expect(newTaskErrors({ expected_time: 0 })).toEqual([
			"Subject is required",
			"Expected start is required",
			"Expected end is required",
			"Task Owner is required",
			"Estimated time must be more than 0 hours",
			"Priority is required",
		])
	})

	it("rejects an end before the start", () => {
		const form = {
			...newTaskDefaults({ subject: "X", today: "2026-11-02", user: "me@example.com", options }),
			exp_end_date: "2026-11-01",
		}
		expect(newTaskErrors(form)).toEqual(["Expected end date cannot be before start date"])
	})
})
