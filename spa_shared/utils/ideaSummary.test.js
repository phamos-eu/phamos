import { describe, expect, it } from "vitest"
import { summaryWithoutTitle } from "./ideaSummary.js"

describe("summaryWithoutTitle", () => {
	it("drops the title at the start of the excerpt", () => {
		expect(summaryWithoutTitle("Weekly idea target Count ideas per week", "Weekly idea target")).toBe(
			"Count ideas per week"
		)
		expect(summaryWithoutTitle("Weekly idea target", "Weekly idea target")).toBe("")
		expect(summaryWithoutTitle("weekly idea target: count", "Weekly idea target")).toBe("count")
	})

	it("leaves other excerpts alone", () => {
		expect(summaryWithoutTitle("Something else entirely", "Weekly idea target")).toBe("Something else entirely")
		expect(summaryWithoutTitle("", "Title")).toBe("")
		expect(summaryWithoutTitle("Text", "")).toBe("Text")
	})
})
