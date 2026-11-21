// Run with `yarn test:spa` (vitest globals, see personal_frontend/vitest.config.js).
import {
	chapterLinks,
	closesPanel,
	ganttData,
	loadPrefs,
	planningRedirect,
	PREFS_KEY,
	proposeDateChangeUrl,
	savePrefs,
	stackFeatures,
} from "./roadmapView.js"

function memoryStorage(initial = {}) {
	const data = { ...initial }
	return {
		data,
		getItem: (key) => (key in data ? data[key] : null),
		setItem: (key, value) => {
			data[key] = String(value)
		},
	}
}

const throwing = {
	getItem() {
		throw new Error("blocked")
	},
	setItem() {
		throw new Error("blocked")
	},
}

describe("remembered zoom and baseline toggle", () => {
	it("starts at months with the baseline off", () => {
		expect(loadPrefs(memoryStorage())).toEqual({ zoom: "month", showBaseline: false })
		expect(loadPrefs(null)).toEqual({ zoom: "month", showBaseline: false })
	})

	it("reads back what was saved", () => {
		const storage = memoryStorage()
		expect(savePrefs(storage, { zoom: "quarter", showBaseline: true })).toBe(true)
		expect(loadPrefs(storage)).toEqual({ zoom: "quarter", showBaseline: true })
	})

	it("works when storage throws or holds rubbish", () => {
		expect(loadPrefs(throwing)).toEqual({ zoom: "month", showBaseline: false })
		expect(savePrefs(throwing, { zoom: "week", showBaseline: true })).toBe(false)
		expect(loadPrefs(memoryStorage({ [PREFS_KEY]: "{not json" }))).toEqual({ zoom: "month", showBaseline: false })
		expect(loadPrefs(memoryStorage({ [PREFS_KEY]: '{"zoom":"year","showBaseline":"yes"}' }))).toEqual({ zoom: "month", showBaseline: false })
	})
})

describe("links", () => {
	it("opens a prefilled date change for the chapter in Desk", () => {
		const url = proposeDateChangeUrl("IMP-0001", "CH 1 & 2")
		expect(url.startsWith("/app/implementation-change/new?")).toBe(true)
		const query = new URLSearchParams(url.split("?")[1])
		expect(Object.fromEntries(query)).toEqual({
			implementation: "IMP-0001",
			change_type: "Dates",
			target_doctype: "Implementation Chapter",
			target_name: "CH 1 & 2",
		})
	})

	it("sends the old Planning page to the Roadmap of the same implementation", () => {
		expect(planningRedirect({ params: { implementation: "IMP-0001" } })).toEqual({
			name: "Roadmap",
			params: { implementation: "IMP-0001" },
		})
	})
})

const roadmap = {
	modules: [
		{
			module: "Sales",
			label: "Sales",
			bars: [
				{
					name: "CH-1",
					chapter: "CH-1",
					title: "Quotations",
					status: "Planned",
					planned_start: "2026-11-02",
					target_date: "2026-11-30",
					current_level: 2,
					target_level: 4,
					critical: true,
					slack_days: 0,
					baseline: { planned_start: "2026-11-02", target_date: "2026-11-20", shift_days: 10 },
				},
				{ name: "CH-2", chapter: "CH-2", title: "Draft idea", status: "Draft", planned_start: "2026-12-01", target_date: "2026-12-10", current_level: null, target_level: 3, critical: null, slack_days: null, baseline: null },
			],
			events: [
				{ name: "F-1", title: "Price list", kind: "planned", date: "2026-11-05", status: "Live" },
				{ name: "F-1", title: "Price list", kind: "finished", date: "2026-11-20", status: "Live" },
				{ name: "F-2", title: "Discounts", kind: "planned", date: "2026-11-06", status: "In Progress" },
			],
		},
		{ module: "HR", label: "HR", bars: [{ name: "item:ROW-1", chapter: null, title: "HR", status: null, planned_start: "2026-11-01", target_date: "2026-12-31", current_level: 1, target_level: 2 }], events: [] },
	],
	no_module: { bars: [], events: [{ name: "F-9", title: "Loose", kind: "planned", date: "2026-11-10" }] },
	dependencies: [{ from: "CH-1", to: "CH-2", conflict: false }],
	markers: [
		{ type: "milestone", name: "MS-1", title: "Sprint 1", date: "2026-11-15", web_url: "https://git.example/ms/1" },
		{ type: "release", name: "REL-1", title: "1.0", date: "2026-11-25", late_features: [{ name: "F-2", title: "Discounts" }] },
	],
}

describe("ganttData", () => {
	const data = ganttData(roadmap)

	it("draws one row per module and No module last", () => {
		expect(data.rows.map((r) => [r.label, r.sublabel])).toEqual([
			["Sales", "2 chapters"],
			["HR", ""],
			["No module", ""],
		])
	})

	it("maps a chapter to a level-step bar with slack, shift and baseline", () => {
		expect(data.rows[0].bars[0]).toEqual({
			name: "CH-1",
			label: "Quotations",
			start: "2026-11-02",
			end: "2026-11-30",
			fromLevel: 2,
			toLevel: 4,
			currentLevel: 2,
			critical: true,
			faded: false,
			slackDays: 0,
			shiftDays: 10,
			baseline: { start: "2026-11-02", end: "2026-11-20" },
		})
	})

	it("fades Draft chapters and draws no level step without a current level", () => {
		expect(data.rows[0].bars[1]).toMatchObject({ faded: true, fromLevel: null, toLevel: 3, baseline: null, shiftDays: null })
	})

	it("turns features into planned and finished dots", () => {
		expect(data.rows[0].events.map((e) => [e.name, e.status])).toEqual([
			["F-1", "planned"],
			["F-1", "finished"],
			["F-2", "planned"],
		])
	})

	it("links milestones to GitLab and lists late features on a release", () => {
		expect(data.markers).toEqual([
			{ name: "MS-1", type: "milestone", title: "Sprint 1", date: "2026-11-15", url: "https://git.example/ms/1", late: [] },
			{ name: "REL-1", type: "release", title: "1.0", date: "2026-11-25", url: null, late: ["Discounts"] },
		])
	})

	it("links a milestone only to an http(s) address", () => {
		const markers = (web_url) => ganttData({ markers: [{ type: "milestone", name: "M", title: "M", date: "2026-11-15", web_url }] }).markers
		expect(markers("javascript:alert(1)")[0].url).toBeNull()
		expect(markers(null)[0].url).toBeNull()
		expect(markers(" http://git.example/ms/2 ")[0].url).toBe("http://git.example/ms/2")
	})

	it("draws nothing without data", () => {
		expect(ganttData(null)).toEqual({ rows: [], dependencies: [], markers: [] })
	})
})

describe("side panel helpers", () => {
	it("finds the chapters a chapter waits for and the ones waiting for it", () => {
		expect(chapterLinks(roadmap, "CH-2").dependsOn.map((b) => b.title)).toEqual(["Quotations"])
		expect(chapterLinks(roadmap, "CH-1").neededBy.map((b) => [b.title, b.module])).toEqual([["Draft idea", "Sales"]])
	})

	it("lists a stack's features with their finished or planned date", () => {
		expect(stackFeatures(roadmap, ["F-1", "F-2", "F-9"])).toEqual([
			{ name: "F-1", title: "Price list", kind: "finished", date: "2026-11-20" },
			{ name: "F-2", title: "Discounts", kind: "planned", date: "2026-11-06" },
			{ name: "F-9", title: "Loose", kind: "planned", date: "2026-11-10" },
		])
	})
})

describe("closesPanel", () => {
	const key = (k, inField = false) => ({ key: k, target: { closest: (selector) => (inField && selector.includes("textarea") ? {} : null) } })

	it("closes on Esc", () => {
		expect(closesPanel(key("Escape"))).toBe(true)
	})

	it("leaves the panel open for other keys, an open popover, or Esc in a field", () => {
		expect(closesPanel(key("Enter"))).toBe(false)
		expect(closesPanel(key("Escape"), true)).toBe(false)
		expect(closesPanel(key("Escape", true))).toBe(false)
	})
})
