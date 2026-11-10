import { readFileSync } from "fs"
import path from "path"
import { beforeEach, describe, expect, it, vi } from "vitest"

// The server call is mocked; the store is tested without a site.
vi.mock("frappe-ui", () => ({ call: vi.fn() }))

const { call } = await import("frappe-ui")
const { endVoteWalk, nextIdeaForVote } = await import("./ideasStore.js")

const rows = (...names) => names.map((name) => ({ name }))
const listCalls = () => call.mock.calls.filter(([method]) => method.endsWith(".get_ideas_for_vote")).length

describe("the Next idea walk (#1845)", () => {
	beforeEach(() => {
		endVoteWalk()
		call.mockReset()
	})

	it("loads the list once per walk and keeps its order while votes reorder it", async () => {
		call.mockResolvedValueOnce(rows("a", "b", "c")).mockResolvedValue(rows("c", "b", "a"))
		expect(await nextIdeaForVote("a")).toEqual({ next: "b", position: 1, total: 3 })
		expect(await nextIdeaForVote("b")).toEqual({ next: "c", position: 2, total: 3 })
		expect(listCalls()).toBe(1)
	})

	it("loads the list again for a new walk, with ideas handed in since", async () => {
		call.mockResolvedValueOnce(rows("a", "b")).mockResolvedValueOnce(rows("a", "b", "new"))
		await nextIdeaForVote("a")
		endVoteWalk()
		expect(await nextIdeaForVote("b")).toEqual({ next: "new", position: 2, total: 3 })
		expect(listCalls()).toBe(2)
	})
})

describe("German strings on the vote page (#1845)", () => {
	// Source strings of phamos/translations/de.csv: the first CSV field, quoted or not.
	const csv = readFileSync(path.resolve(__dirname, "../../phamos/translations/de.csv"), "utf8")
	const sources = new Set(csv.split("\n").map((line) => (line.startsWith('"') ? line.slice(1).split('",')[0] : line.split(",")[0])))

	it.each(["{0} of {1}", "Next idea", "Last idea up for vote"])("has a German entry for %s", (text) => {
		expect(sources.has(text)).toBe(true)
	})
})
