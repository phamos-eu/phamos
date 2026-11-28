import { describe, expect, it } from "vitest"
import { detailsSummary, entryLine, typeLabel, typeTheme, versionsLine } from "./phriendReport.js"

describe("phriendReport", () => {
	it("names the type as Phriend does", () => {
		expect(typeLabel("Other")).toBe("Something else")
		expect(typeLabel("Bug")).toBe("Bug")
		expect(typeTheme("Bug")).toBe("red")
		expect(typeTheme("Other")).toBe("gray")
		expect(typeLabel("Improvement")).toBe("Improvement") // was "Idea" (#1924)
		expect(typeTheme("Improvement")).toBe("blue")
	})

	it("sums the details up in one line", () => {
		expect(
			detailsSummary({
				browser: "Chrome 156, macOS",
				viewport: "1440x900 @1x",
				versions: { phamos: "15.140.0", frappe: "15.118.0" },
				recent_errors: [{}, {}],
				failed_requests: [{}],
			}),
		).toBe("Chrome 156, macOS · 1440x900 @1x · phamos 15.140.0 · 2 errors · 1 failed request")
		expect(detailsSummary({})).toBe("no errors")
	})

	it("writes an error or failed request as one line", () => {
		expect(entryLine({ status: "500", method: "POST", url: "/api/method/x", message: "Server Error" })).toBe(
			"500 POST /api/method/x: Server Error",
		)
		expect(entryLine({ type: "error", message: "boom", source: "/assets/a.js:1:2" })).toBe("/assets/a.js:1:2: boom")
		expect(entryLine({ type: "unhandledrejection" })).toBe("unhandledrejection")
	})

	it("lists the versions with phamos first", () => {
		expect(versionsLine({ frappe: "15.1", phamos: "15.140.0", erpnext: "15.2", empty: "" })).toBe(
			"phamos 15.140.0, erpnext 15.2, frappe 15.1",
		)
	})
})
