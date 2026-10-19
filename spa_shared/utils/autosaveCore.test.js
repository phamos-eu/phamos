// Run with `yarn test:spa` (vitest globals: describe/it/expect/vi).
import {
	compareModified,
	computeDirtyFields,
	createCoalescedRunner,
	createSaveScheduler,
	fieldEquals,
	fromServerValue,
	isEmptyValue,
	isEmptyHtml,
	mergeServerDoc,
	normalizeHtml,
	toServerValue,
} from "./autosaveCore.js"

const defs = {
	subject: { kind: "text", trim: true, required: true },
	description: { kind: "html" },
	priority: { kind: "select" },
	progress: { kind: "number" },
}

describe("html helpers", () => {
	it("treats empty editor output as empty", () => {
		for (const v of ["", null, "<p></p>", "<p><br></p>", "<p>&nbsp;</p>", " <p> </p> "]) {
			expect(isEmptyHtml(v)).toBe(true)
			expect(normalizeHtml(v)).toBe("")
		}
		expect(isEmptyHtml('<p><img src="/files/a.png"></p>')).toBe(false)
	})

	it("ignores formatting noise but not content", () => {
		expect(normalizeHtml("<p>a</p>\n  <p>b</p>")).toBe(normalizeHtml("<p>a</p><p>b</p>"))
		expect(normalizeHtml("<p>a</p><p></p><p><br></p>")).toBe("<p>a</p>")
		expect(normalizeHtml("<p>a</p>")).not.toBe(normalizeHtml("<p>ab</p>"))
	})
})

describe("fieldEquals / toServerValue", () => {
	it("compares by kind", () => {
		expect(fieldEquals(defs.subject, " x ", "x")).toBe(true)
		expect(fieldEquals(defs.priority, null, "")).toBe(true)
		expect(fieldEquals(defs.progress, "0", null)).toBe(true)
		expect(fieldEquals(defs.description, "<p>a</p>", "<p>a</p><p></p>")).toBe(true)
	})

	it("sends normalised values", () => {
		expect(toServerValue(defs.subject, "  Hi ")).toBe("Hi")
		expect(toServerValue(defs.description, "<p><br></p>")).toBe("")
		expect(toServerValue(defs.description, "<p>x</p>")).toBe("<p>x</p>")
	})
})

describe("dirty tracking", () => {
	it("is relative to the last synced value, not the server echo", () => {
		// We sent "<p>see https://x.io</p>"; the server linkified it. Nothing was
		// typed since, so the field must be clean and no save loop may start.
		const sent = "<p>see https://x.io</p>"
		const merged = mergeServerDoc({
			defs,
			server: { description: '<p>see <a href="https://x.io">https://x.io</a></p>' },
			draft: { description: sent },
			baseline: { description: "<p>old</p>" },
			lastSynced: { description: sent },
			source: "save",
		})
		expect(computeDirtyFields(defs, merged.draft, merged.lastSynced)).toEqual([])
	})

	it("lists only changed fields", () => {
		const synced = { subject: "A", description: "<p>x</p>", priority: "Low", progress: 0 }
		const draft = { ...synced, description: "<p>xy</p>" }
		expect(computeDirtyFields(defs, draft, synced)).toEqual(["description"])
	})
})

describe("mergeServerDoc", () => {
	const base = { subject: "A", description: "<p>one</p>", priority: "Low", progress: 0 }

	it("keeps text typed while a save was in flight", () => {
		const merged = mergeServerDoc({
			defs,
			server: { ...base, description: "<p>one two</p>" },
			draft: { ...base, description: "<p>one two three</p>" },
			baseline: base,
			lastSynced: { ...base, description: "<p>one two</p>" },
			source: "save",
		})
		expect(merged.draft.description).toBe("<p>one two three</p>")
		expect(merged.conflicts).toEqual([])
	})

	it("adopts clean fields changed by someone else", () => {
		const merged = mergeServerDoc({
			defs,
			server: { ...base, priority: "High" },
			draft: base,
			baseline: base,
			lastSynced: base,
			source: "realtime",
		})
		expect(merged.draft.priority).toBe("High")
		expect(merged.lastSynced.priority).toBe("High")
	})

	it("reports a conflict when both sides changed the same field", () => {
		const merged = mergeServerDoc({
			defs,
			server: { ...base, description: "<p>theirs</p>" },
			draft: { ...base, description: "<p>mine</p>" },
			baseline: base,
			lastSynced: base,
			source: "realtime",
		})
		expect(merged.draft.description).toBe("<p>mine</p>")
		expect(merged.conflicts).toEqual(["description"])
	})

	it("defers clean focused fields instead of moving the cursor", () => {
		const merged = mergeServerDoc({
			defs,
			server: { ...base, description: "<p>theirs</p>" },
			draft: base,
			baseline: base,
			lastSynced: base,
			focused: new Set(["description"]),
			source: "realtime",
		})
		expect(merged.draft.description).toBe("<p>one</p>")
		expect(merged.deferred.description).toBe("<p>theirs</p>")
	})

	it("leaves fields missing from a partial payload alone", () => {
		const merged = mergeServerDoc({
			defs,
			server: { priority: "High" },
			draft: base,
			baseline: base,
			lastSynced: base,
			source: "prop",
		})
		expect(merged.draft.description).toBe("<p>one</p>")
		expect(merged.draft.priority).toBe("High")
	})
})

describe("compareModified", () => {
	it("pads the fraction Frappe drops when it is zero", () => {
		expect(compareModified("2026-10-13 11:21:23", "2026-10-13 11:21:23.000000")).toBe(0)
		expect(compareModified("2026-10-13 11:21:23.5", "2026-10-13 11:21:23.400000")).toBe(1)
		expect(compareModified("2026-10-13 11:21:22.999999", "2026-10-13 11:21:23")).toBe(-1)
		expect(compareModified(null, "2026-01-01 00:00:00")).toBe(-1)
	})
})

describe("createSaveScheduler", () => {
	beforeEach(() => vi.useFakeTimers())
	afterEach(() => vi.useRealTimers())

	it("runs once after the user pauses", () => {
		const run = vi.fn()
		const s = createSaveScheduler({ wait: 500, maxWait: 3000, run })
		s.schedule()
		vi.advanceTimersByTime(400)
		s.schedule()
		vi.advanceTimersByTime(400)
		expect(run).not.toHaveBeenCalled()
		vi.advanceTimersByTime(100)
		expect(run).toHaveBeenCalledTimes(1)
	})

	it("still saves during continuous typing (maxWait)", () => {
		const run = vi.fn()
		const s = createSaveScheduler({ wait: 500, maxWait: 3000, run })
		for (let t = 0; t < 3000; t += 100) {
			s.schedule()
			vi.advanceTimersByTime(100)
		}
		expect(run).toHaveBeenCalledTimes(1)
	})

	it("flushes immediately and cancels cleanly", () => {
		const run = vi.fn()
		const s = createSaveScheduler({ wait: 500, run })
		s.schedule()
		s.flush()
		expect(run).toHaveBeenCalledTimes(1)
		vi.advanceTimersByTime(5000)
		expect(run).toHaveBeenCalledTimes(1)
		s.schedule()
		s.cancel()
		vi.advanceTimersByTime(5000)
		expect(run).toHaveBeenCalledTimes(1)
		expect(s.isPending()).toBe(false)
	})
})

describe("createCoalescedRunner", () => {
	it("never drops a run requested while one is in flight", async () => {
		let release
		const calls = []
		const runner = createCoalescedRunner(async () => {
			calls.push(calls.length)
			if (calls.length === 1) await new Promise((r) => (release = r))
		})
		const first = runner.run()
		runner.run()
		runner.run()
		expect(runner.isRunning()).toBe(true)
		release()
		await first
		// One for the original call, exactly one follow-up for the two extra calls.
		expect(calls).toEqual([0, 1])
		expect(runner.isRunning()).toBe(false)
	})
})

describe("json kind (child table rows)", () => {
	const def = { kind: "json" }
	it("compares by value, not identity", () => {
		expect(fieldEquals(def, [{ a: 1 }], [{ a: 1 }])).toBe(true)
		expect(fieldEquals(def, [{ a: 1 }], [{ a: 2 }])).toBe(false)
		expect(fieldEquals(def, null, undefined)).toBe(true)
	})
	it("copies server values so edits never touch the server copy", () => {
		const server = [{ qty: 1 }]
		const local = fromServerValue(def, server)
		local[0].qty = 5
		expect(server[0].qty).toBe(1)
		expect(fromServerValue(def, null)).toEqual([])
	})
	it("treats an empty list as empty", () => {
		expect(isEmptyValue(def, [])).toBe(true)
		expect(isEmptyValue(def, [{}])).toBe(false)
		expect(toServerValue(def, undefined)).toEqual([])
	})
})
