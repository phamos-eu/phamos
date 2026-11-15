import {
	definePanel,
	applyCockpitOverride,
	panelsFor,
	dockWidth,
	toggled,
	moved,
	DEFAULT_DOCK_WIDTH,
	MAX_DOCK_WIDTH,
} from "./registry.js"

const checklists = definePanel({ id: "checklists", title: "Checklists", doctypes: ["Issue", "Lead"], order: 20 })
const phriend = definePanel({
	id: "phriend",
	title: "Phriend report",
	doctypes: ["Issue"],
	order: 10,
	when: (r) => !!r.phriend,
	defaultOpen: () => true,
})
const chat = definePanel({ id: "chat", title: "Chat", doctypes: ["Issue"], order: 30, minWidth: 768, defaultOpen: () => false })
const all = [checklists, phriend, chat]
const ids = (panels) => panels.map((p) => p.def.id)

describe("definePanel", () => {
	it("fills defaults and refuses incomplete declarations", () => {
		expect(checklists.when({})).toBe(true)
		expect(checklists.minWidth).toBe(0)
		expect(() => definePanel({ doctypes: ["Issue"] })).toThrow()
		expect(() => definePanel({ id: "x", doctypes: [] })).toThrow()
	})
})

describe("panelsFor", () => {
	it("shows only panels of the doctype whose condition holds, in declared order", () => {
		expect(ids(panelsFor(all, { doctype: "Issue", record: { phriend: {} } }))).toEqual(["phriend", "checklists", "chat"])
		expect(ids(panelsFor(all, { doctype: "Issue", record: {} }))).toEqual(["checklists", "chat"])
		expect(ids(panelsFor(all, { doctype: "Lead", record: {} }))).toEqual(["checklists"])
	})

	it("returns nothing without a record", () => {
		expect(panelsFor(all, { doctype: "Issue", record: null })).toEqual([])
	})

	it("hides a panel whose condition throws", () => {
		const broken = definePanel({ id: "broken", doctypes: ["Issue"], when: () => { throw new Error("x") } })
		expect(ids(panelsFor([broken, checklists], { doctype: "Issue", record: {} }))).toEqual(["checklists"])
	})

	it("applies the cockpit override: hide, order, add", () => {
		const notes = { id: "notes", title: "Notes", doctypes: ["Issue"] }
		const cockpitPanels = { Issue: { hide: ["chat"], order: ["notes", "checklists"], add: [notes] } }
		expect(ids(panelsFor(all, { doctype: "Issue", record: { phriend: {} }, cockpitPanels }))).toEqual([
			"notes",
			"checklists",
			"phriend",
		])
	})

	it("puts the user's order above the cockpit's and ignores unknown ids", () => {
		const layout = { order: ["gone", "chat", "checklists", "phriend"] }
		expect(ids(panelsFor(all, { doctype: "Issue", record: { phriend: {} }, layout }))).toEqual([
			"chat",
			"checklists",
			"phriend",
		])
	})

	it("keeps a panel the user never ordered at its declared place", () => {
		// the user ordered phriend and checklists before the chat existed (order 5)
		const early = definePanel({ id: "early", doctypes: ["Issue"], order: 1 })
		const layout = { order: ["checklists", "phriend"] }
		expect(ids(panelsFor([early, ...all], { doctype: "Issue", record: { phriend: {} }, layout }))).toEqual([
			"early",
			"checklists",
			"phriend",
			"chat",
		])
	})

	it("expands by default unless the user switched the panel", () => {
		const record = { phriend: {} }
		const byId = (layout) =>
			Object.fromEntries(panelsFor(all, { doctype: "Issue", record, layout }).map((p) => [p.def.id, p.expanded]))
		expect(byId({})).toEqual({ phriend: true, checklists: true, chat: false })
		expect(byId({ collapsed: ["phriend"], expanded: ["chat"] })).toEqual({ phriend: false, checklists: true, chat: true })
	})
})

describe("applyCockpitOverride", () => {
	it("returns a sorted copy without an override", () => {
		const list = applyCockpitOverride(all, undefined)
		expect(list.map((d) => d.id)).toEqual(["phriend", "checklists", "chat"])
		expect(list).not.toBe(all)
	})
})

describe("dockWidth", () => {
	const panels = panelsFor(all, { doctype: "Issue", record: {} })
	it("uses the user's width, else the default", () => {
		expect(dockWidth(panels, undefined)).toBe(DEFAULT_DOCK_WIDTH)
		expect(dockWidth(panels, 400)).toBe(400)
	})
	it("is 768 while the chat is expanded and falls back when it is collapsed", () => {
		const withChat = (expanded) => panels.map((p) => ({ ...p, expanded: p.def.id === "chat" ? expanded : p.expanded }))
		expect(dockWidth(withChat(true), undefined)).toBe(768)
		expect(dockWidth(withChat(false), undefined)).toBe(DEFAULT_DOCK_WIDTH)
		expect(dockWidth(withChat(false), 500)).toBe(500)
	})

	it("keeps a separate width while the chat is expanded", () => {
		const withChat = (expanded) => panels.map((p) => ({ ...p, expanded: p.def.id === "chat" ? expanded : p.expanded }))
		expect(dockWidth(withChat(true), 400, 900)).toBe(900)
		expect(dockWidth(withChat(false), 400, 900)).toBe(400)
		// never below what the chat needs
		expect(dockWidth(withChat(true), 400, 500)).toBe(768)
	})

	it("widens while a wide panel is expanded and clamps", () => {
		const open = panels.map((p) => ({ ...p, expanded: true }))
		expect(dockWidth(open, 400)).toBe(768)
		expect(dockWidth(panels, 99999)).toBe(MAX_DOCK_WIDTH)
		expect(dockWidth(panels, 10)).toBe(240)
	})
})

describe("toggled", () => {
	it("stores only deviations from the default", () => {
		let layout = toggled({}, "checklists", false, true)
		expect(layout).toEqual({ collapsed: ["checklists"], expanded: [] })
		layout = toggled(layout, "checklists", true, true)
		expect(layout).toEqual({ collapsed: [], expanded: [] })
		layout = toggled(layout, "chat", true, false)
		expect(layout.expanded).toEqual(["chat"])
	})
	it("keeps other keys", () => {
		expect(toggled({ width: 500 }, "a", false, true).width).toBe(500)
	})
})

describe("moved", () => {
	it("moves within the shown panels and keeps unseen ids after them", () => {
		const layout = { order: ["phriend", "checklists", "chat"], width: 300 }
		expect(moved(layout, ["checklists", "chat"], "chat", -1)).toEqual({
			order: ["chat", "checklists", "phriend"],
			width: 300,
		})
	})
	it("does nothing at the edges", () => {
		const layout = { order: ["a", "b"] }
		expect(moved(layout, ["a", "b"], "a", -1)).toBe(layout)
		expect(moved(layout, ["a", "b"], "b", 1)).toBe(layout)
	})
})
