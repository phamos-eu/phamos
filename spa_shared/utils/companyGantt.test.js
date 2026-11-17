// Run with `yarn test:spa` (vitest globals, see personal_frontend/vitest.config.js).
import { buildCompanyRows, groupRowName, groupSpan, isGroupRow, matchesSearch } from "./companyGantt.js"

const task = (name, start, end, extra = {}) => ({
	name,
	subject: `Task ${name}`,
	exp_start_date: start,
	exp_end_date: end,
	depends_on_tasks: "",
	...extra,
})

const GROUPS = [
	{
		department: "Management",
		label: "General Management",
		color: "#a16207",
		own: true,
		tasks: [task("GM-1", "2026-11-01", "2026-12-31")],
	},
	{
		department: "Sales",
		label: "Sales",
		color: "#c2410c",
		own: false,
		tasks: [
			task("S-1", "2026-10-15", "2026-11-20", { depends_on_tasks: "S-2,SUB-9" }),
			task("S-2", "2026-12-01", "2027-02-28"),
		],
	},
	{ department: "HR", label: "Human Resources", color: "#be123c", own: false, tasks: [] },
]

describe("company gantt rows", () => {
	it("puts a header row before each department's tasks, in the given order", () => {
		const rows = buildCompanyRows(GROUPS, { fallbackDate: "2026-11-17" })
		expect(rows.map((r) => r.name)).toEqual([
			"group:Management",
			"GM-1",
			"group:Sales",
			"S-1",
			"S-2",
			"group:HR",
		])
		expect(rows.filter((r) => r.is_group).map((r) => r.group_count)).toEqual([1, 2, 0])
	})

	it("gives the header the department's span as its summary bar", () => {
		const header = buildCompanyRows(GROUPS).find((r) => r.name === "group:Sales")
		expect([header.exp_start_date, header.exp_end_date]).toEqual(["2026-10-15", "2027-02-28"])
		expect(header.locked).toBe(true)
		expect(header.empty).toBe(false)
	})

	it("marks a department without dated tasks as empty, on the fallback date", () => {
		const header = buildCompanyRows(GROUPS, { fallbackDate: "2026-11-17" }).find((r) => r.name === "group:HR")
		expect(header.empty).toBe(true)
		expect(header.exp_start_date).toBe("2026-11-17")
	})

	it("colours tasks in the cockpit colour and locks other departments' tasks", () => {
		const rows = buildCompanyRows(GROUPS)
		const own = rows.find((r) => r.name === "GM-1")
		const other = rows.find((r) => r.name === "S-1")
		expect([own.color, own.locked]).toEqual(["#a16207", false])
		expect([other.color, other.locked]).toEqual(["#c2410c", true])
	})

	it("hides the tasks of collapsed departments but keeps their header", () => {
		const rows = buildCompanyRows(GROUPS, { collapsed: ["Sales"] })
		expect(rows.map((r) => r.name)).toEqual(["group:Management", "GM-1", "group:Sales", "group:HR"])
		expect(rows.find((r) => r.name === "group:Sales").collapsed).toBe(true)
	})

	it("leaves out departments without a match while searching", () => {
		const rows = buildCompanyRows(GROUPS, { search: "s-2" })
		expect(rows.map((r) => r.name)).toEqual(["group:Sales", "S-2"])
	})

	it("drops dependencies on tasks that are not shown", () => {
		const s1 = buildCompanyRows(GROUPS).find((r) => r.name === "S-1")
		expect(s1.depends_on_tasks).toBe("S-2")
	})
})

describe("company gantt helpers", () => {
	it("recognises header rows", () => {
		expect(isGroupRow(groupRowName("Sales"))).toBe(true)
		expect(isGroupRow("TASK-0001")).toBe(false)
	})

	it("has no span without dated tasks", () => {
		expect(groupSpan([task("X", null, null)])).toBeNull()
	})

	it("searches subject, status and assignees", () => {
		expect(matchesSearch({ subject: "Budget", assignee_names: ["Ada"] }, "ada")).toBe(true)
		expect(matchesSearch({ subject: "Budget" }, "plan")).toBe(false)
	})
})
