import { describe, expect, it } from "vitest"
import { withOwnRoutes } from "./routes.js"

describe("withOwnRoutes", () => {
	const shared = [
		{ path: "/issues", name: "Issues", component: "SharedIssues" },
		{ path: "/issues/list", name: "IssuesList", component: "List" },
	]

	it("replaces a shared route of the same name and keeps the rest", () => {
		const routes = withOwnRoutes(shared, [{ path: "/issues", name: "Issues", component: "MyIssues" }])
		expect(routes.map((r) => `${r.name}:${r.component}`)).toEqual(["IssuesList:List", "Issues:MyIssues"])
	})

	it("adds routes without a name and leaves shared routes alone without own ones", () => {
		expect(withOwnRoutes(shared)).toEqual(shared)
		expect(withOwnRoutes(shared, [{ path: "/x" }])).toHaveLength(3)
	})
})
