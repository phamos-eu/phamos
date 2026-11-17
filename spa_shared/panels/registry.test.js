import { definePanel, applyCockpitOverride, panelsFor, minimums, places } from "./registry.js"

const checklists = definePanel({ id: "checklists", title: "Checklists", doctypes: ["Issue", "Lead"] })
const phriend = definePanel({ id: "phriend", title: "Phriend report", doctypes: ["Issue"], when: (r) => !!r.phriend })
const chat = definePanel({ id: "chat", title: "Chat", doctypes: ["Issue"], minWidth: 768, minHeight: 320 })
const all = [chat, phriend, checklists]
const ids = (defs) => defs.map((d) => d.id)

describe("definePanel", () => {
	it("fills defaults and refuses incomplete declarations", () => {
		expect(checklists.when({})).toBe(true)
		expect(checklists.minWidth).toBe(240)
		expect(checklists.minHeight).toBe(120)
		expect(() => definePanel({ doctypes: ["Issue"] })).toThrow()
		expect(() => definePanel({ id: "x", doctypes: [] })).toThrow()
	})
})

describe("panelsFor", () => {
	it("shows only panels of the doctype whose condition holds, in declared order", () => {
		expect(ids(panelsFor(all, { doctype: "Issue", record: { phriend: {} } }))).toEqual(["chat", "phriend", "checklists"])
		expect(ids(panelsFor(all, { doctype: "Issue", record: {} }))).toEqual(["chat", "checklists"])
		expect(ids(panelsFor(all, { doctype: "Lead", record: {} }))).toEqual(["checklists"])
	})

	it("returns nothing without a record", () => {
		expect(panelsFor(all, { doctype: "Issue", record: null })).toEqual([])
	})

	it("hides a panel whose condition throws", () => {
		const broken = definePanel({ id: "broken", doctypes: ["Issue"], when: () => { throw new Error("x") } })
		expect(ids(panelsFor([broken, checklists], { doctype: "Issue", record: {} }))).toEqual(["checklists"])
	})

	it("applies the cockpit override: hide and add", () => {
		const notes = { id: "notes", title: "Notes", doctypes: ["Issue"] }
		const cockpitPanels = { Issue: { hide: ["chat"], add: [notes] } }
		expect(ids(panelsFor(all, { doctype: "Issue", record: { phriend: {} }, cockpitPanels }))).toEqual([
			"phriend",
			"checklists",
			"notes",
		])
	})
})

describe("applyCockpitOverride", () => {
	it("returns a copy without an override", () => {
		const list = applyCockpitOverride(all, undefined)
		expect(list).toEqual(all)
		expect(list).not.toBe(all)
	})
})

describe("minimums and places", () => {
	it("maps panel ids to their sizes and default places", () => {
		expect(minimums(all).chat).toEqual({ w: 768, h: 320 })
		const notes = definePanel({ id: "notes", doctypes: ["Issue"], place: { near: "checklists", side: "bottom" } })
		expect(places([...all, notes])).toEqual({ notes: { near: "checklists", side: "bottom" } })
	})
})
