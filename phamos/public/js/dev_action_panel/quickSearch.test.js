import { describe, expect, it } from "vitest"
import { issueMatchesSearch, projectMatchesSearch, sortIssues } from "./quickSearch.js"

const issue = (over = {}) => ({
	name: "GI-1",
	issue_id: 2211,
	title: "Reverse Searchbar",
	project_name: "phamos",
	assignee: "Muhammad Ali Baig",
	labels: "phriend, P:2",
	parent_issue_id: 1895,
	...over,
})

describe("issueMatchesSearch", () => {
	it("matches everything on an empty query", () => {
		expect(issueMatchesSearch(issue(), "")).toBe(true)
		expect(issueMatchesSearch(issue(), "   ")).toBe(true)
	})
	it("finds by title, number with or without #, project, assignee, label, parent", () => {
		for (const q of ["searchbar", "2211", "#2211", "PHAMOS", "ali baig", "phriend", "#1895"]) {
			expect(issueMatchesSearch(issue(), q)).toBe(true)
		}
	})
	it("needs every word to match somewhere", () => {
		expect(issueMatchesSearch(issue(), "reverse phriend")).toBe(true)
		expect(issueMatchesSearch(issue(), "reverse kefiya")).toBe(false)
	})
	it("copes with missing fields", () => {
		expect(issueMatchesSearch({ name: "GI-2" }, "x")).toBe(false)
	})
})

describe("projectMatchesSearch", () => {
	const p = { name: "PROJ-0042", project_name: "suncycle", customer_desc: "suncycle GmbH", status: "Open" }
	it("finds by name, ID, customer and status", () => {
		for (const q of ["sun", "proj-0042", "gmbh", "open"]) expect(projectMatchesSearch(p, q)).toBe(true)
		expect(projectMatchesSearch(p, "zam")).toBe(false)
	})
})

describe("sortIssues", () => {
	const a = issue({ name: "a", issue_id: 3, title: "beta", due_date: "2026-12-01", labels: "P:3", project_name: "b" })
	const b = issue({ name: "b", issue_id: 10, title: "Alpha", due_date: null, labels: "", project_name: "a" })
	const c = issue({ name: "c", issue_id: 1, title: "gamma", due_date: "2026-11-01", labels: "P:1", project_name: "c" })
	const names = (list) => list.map((i) => i.name)

	it("defaults to due date ascending with no due date last", () => {
		expect(names(sortIssues([a, b, c]))).toEqual(["c", "a", "b"])
	})
	it("keeps no due date last when descending", () => {
		expect(names(sortIssues([a, b, c], "due_date:desc"))).toEqual(["a", "c", "b"])
	})
	it("sorts by number numerically", () => {
		expect(names(sortIssues([a, b, c], "id:asc"))).toEqual(["c", "a", "b"])
		expect(names(sortIssues([a, b, c], "id:desc"))).toEqual(["b", "a", "c"])
	})
	it("sorts by title and project case-insensitively", () => {
		expect(names(sortIssues([a, b, c], "title:asc"))).toEqual(["b", "a", "c"])
		expect(names(sortIssues([a, b, c], "project:asc"))).toEqual(["b", "a", "c"])
	})
	it("sorts by priority label, none last", () => {
		expect(names(sortIssues([a, b, c], "priority:asc"))).toEqual(["c", "a", "b"])
	})
	it("does not mutate the input", () => {
		const list = [a, b, c]
		sortIssues(list, "id:desc")
		expect(names(list)).toEqual(["a", "b", "c"])
	})
})
