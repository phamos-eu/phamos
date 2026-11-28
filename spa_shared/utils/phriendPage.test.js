import { describe, expect, it } from "vitest"
import { RECORD_ROUTES, badgeArgs, pageContext } from "./phriendPage.js"

const sales = { base: "/sales-cockpit", cockpit: "Sales", heading: "Leads · Follow-ups" }

describe("pageContext", () => {
	it("refers to the record on a detail route", () => {
		const ctx = pageContext(
			{ name: "LeadDetail", path: "/leads/follow-ups/CRM-LEAD-0001", params: { name: "CRM-LEAD-0001" }, query: {} },
			sales,
			(text) => (text === "Lead" ? "Interessent" : text)
		)
		expect(ctx.ref_doctype).toBe("Lead")
		expect(ctx.ref_docname).toBe("CRM-LEAD-0001")
		expect(ctx.where).toBe("Interessent CRM-LEAD-0001")
		expect(ctx.route).toBe("sales-cockpit/leads/follow-ups/CRM-LEAD-0001")
		expect(ctx.context.route.name).toBe("LeadDetail")
	})

	it("keeps only the keys of the query: its values can be names or search terms", () => {
		const ctx = pageContext({ name: "Leads", path: "/leads", params: {}, query: { search: "Jane Doe", page: "2" } }, sales)
		expect(ctx.context.route.query).toEqual(["search", "page"])
	})

	it("refers to the page on a list or overview route", () => {
		const ctx = pageContext({ name: "LeadsFollowUps", path: "/leads/follow-ups", params: {} }, sales)
		expect(ctx.ref_doctype).toBeNull()
		expect(ctx.ref_docname).toBeNull()
		expect(ctx.where).toBe("Sales · Leads · Follow-ups")
		expect(ctx.route).toBe("sales-cockpit/leads/follow-ups")
	})

	it("treats a detail route without a name as a page", () => {
		const ctx = pageContext({ name: "IssueDetail", path: "/issues/list/", params: {} }, sales)
		expect(ctx.ref_doctype).toBeNull()
	})

	it("keeps the route within the 140 characters of phriend_route", () => {
		const ctx = pageContext({ name: "X", path: `/${"a".repeat(300)}`, params: {} }, sales)
		expect(ctx.route.length).toBe(140)
	})

	it("knows a DocType for every detail route of the six cockpits", () => {
		for (const name of ["IssueDetail", "TaskDetail", "ChecklistDetail", "LeadDetail", "ReceiptDetail", "ContractDetail", "WeeklyMonitoringDetail", "TodoDetail", "IdeaDetail"]) {
			expect(RECORD_ROUTES[name]).toBeTruthy()
		}
	})
})

describe("badgeArgs", () => {
	it("counts by record when there is one, else by page", () => {
		expect(badgeArgs({ ref_doctype: "Lead", ref_docname: "L-1", route: "x" })).toEqual({ ref_doctype: "Lead", ref_docname: "L-1" })
		expect(badgeArgs({ ref_doctype: null, route: "sales-cockpit/leads" })).toEqual({ route: "sales-cockpit/leads" })
	})
})
