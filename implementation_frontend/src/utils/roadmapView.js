// The Roadmap page's logic without Vue or the DOM (#2035), so Vitest covers it: turning
// get_roadmap (#2033) into RoadmapGantt rows (#2034), the viewer's remembered settings, the Desk
// link for "Propose a date change" and the redirect of the old Planning page.

export const ZOOMS = ["week", "month", "quarter"]
export const PREFS_KEY = "implementation-cockpit-roadmap"
const DEFAULT_PREFS = { zoom: "month", showBaseline: false }

// Staff see these chapters faded; customers don't get them from the server.
const FADED_STATUSES = ["Draft", "Cancelled"]

/**
 * Zoom and baseline toggle as this viewer left them. Storage may be missing or throw (private
 * windows, blocked site data): the defaults apply then.
 */
export function loadPrefs(storage) {
	try {
		const saved = JSON.parse(storage?.getItem(PREFS_KEY) || "null") || {}
		return {
			zoom: ZOOMS.includes(saved.zoom) ? saved.zoom : DEFAULT_PREFS.zoom,
			showBaseline: saved.showBaseline === true,
		}
	} catch (e) {
		return { ...DEFAULT_PREFS }
	}
}

/** Remembers zoom and toggle; a storage that throws is ignored (the page works without it). */
export function savePrefs(storage, prefs) {
	try {
		storage?.setItem(PREFS_KEY, JSON.stringify({ zoom: prefs.zoom, showBaseline: Boolean(prefs.showBaseline) }))
		return true
	} catch (e) {
		return false
	}
}

/** The old Planning placeholder now opens the Roadmap of the same implementation. */
export function planningRedirect(to) {
	return { name: "Roadmap", params: { implementation: to.params.implementation } }
}

/**
 * Desk's new Implementation Change form, prefilled through the URL (Frappe reads the query as
 * route options): a date change for this chapter (#1694 decision 8).
 */
export function proposeDateChangeUrl(implementation, chapter) {
	const query = new URLSearchParams({
		implementation,
		change_type: "Dates",
		target_doctype: "Implementation Chapter",
		target_name: chapter,
	})
	return `/app/implementation-change/new?${query.toString()}`
}

// `web_url` is an editable field: only http(s) links become an href, never `javascript:`.
function safeUrl(url) {
	return typeof url === "string" && /^https?:\/\//i.test(url.trim()) ? url.trim() : null
}

function toBar(bar) {
	const current = bar.current_level ?? null
	const target = bar.target_level ?? null
	return {
		name: bar.name,
		label: bar.title || bar.name,
		start: bar.planned_start,
		end: bar.target_date,
		// The chapter climbs from where it is now to its target: "L2 → L4", full once reached.
		// get_roadmap has no starting level, so the step shows what is still ahead; without a
		// current level there is no step to draw.
		fromLevel: target && current !== null ? Math.min(current, target) : null,
		toLevel: target,
		currentLevel: current,
		critical: Boolean(bar.critical),
		faded: FADED_STATUSES.includes(bar.status),
		slackDays: bar.slack_days ?? null,
		shiftDays: bar.baseline?.shift_days ?? null,
		baseline: bar.baseline?.planned_start && bar.baseline?.target_date ? { start: bar.baseline.planned_start, end: bar.baseline.target_date } : null,
	}
}

function toEvent(event) {
	return { name: event.name, label: event.title || event.name, date: event.date, status: event.kind === "finished" ? "finished" : "planned" }
}

function chapterCount(bars) {
	return bars.filter((b) => b.chapter).length
}

/**
 * get_roadmap → RoadmapGantt props. One row per module; "No module" last, only when it has
 * something to draw. `translate` is `__`, passed in so this file stays free of the boot data.
 */
export function ganttData(roadmap, translate = (text, args) => text.replace(/\{(\d+)\}/g, (_, i) => args?.[i] ?? "")) {
	if (!roadmap) return { rows: [], dependencies: [], markers: [] }
	const sublabel = (bars) => {
		const n = chapterCount(bars)
		return n ? translate(n === 1 ? "1 chapter" : "{0} chapters", [n]) : ""
	}
	const rows = (roadmap.modules || []).map((m) => ({
		name: `module:${m.module}`,
		label: m.label || m.module,
		sublabel: sublabel(m.bars || []),
		bars: (m.bars || []).map(toBar),
		events: (m.events || []).map(toEvent),
	}))
	const none = roadmap.no_module || {}
	if ((none.bars || []).length || (none.events || []).length) {
		rows.push({
			name: "module:",
			label: translate("No module"),
			sublabel: sublabel(none.bars || []),
			bars: (none.bars || []).map(toBar),
			events: (none.events || []).map(toEvent),
		})
	}
	const markers = (roadmap.markers || []).map((m) => ({
		name: m.name,
		type: m.type,
		title: m.title,
		date: m.date,
		url: m.type === "milestone" ? safeUrl(m.web_url) : null,
		late: (m.late_features || []).map((f) => f.title || f.name),
	}))
	return { rows, dependencies: roadmap.dependencies || [], markers }
}

/** Every bar of the roadmap by name, with the module row it sits on. */
export function barsByName(roadmap) {
	const out = new Map()
	const rows = [...(roadmap?.modules || []), { module: null, ...(roadmap?.no_module || {}) }]
	for (const row of rows) for (const bar of row.bars || []) out.set(bar.name, { ...bar, module: row.module })
	return out
}

/** Chapters this one waits for, and the ones waiting for it, as bars (for the side panel). */
export function chapterLinks(roadmap, name) {
	const bars = barsByName(roadmap)
	const deps = roadmap?.dependencies || []
	const pick = (list) => list.filter((n) => bars.has(n)).map((n) => bars.get(n))
	return {
		dependsOn: pick(deps.filter((d) => d.to === name).map((d) => d.from)),
		neededBy: pick(deps.filter((d) => d.from === name).map((d) => d.to)),
	}
}

/** A feature's dots of the roadmap, for the stack list: title, planned or finished, date. */
export function stackFeatures(roadmap, names) {
	const events = [...(roadmap?.modules || []).flatMap((m) => m.events || []), ...(roadmap?.no_module?.events || [])]
	return (names || []).map((name) => {
		const own = events.filter((e) => e.name === name)
		const finished = own.find((e) => e.kind === "finished")
		const shown = finished || own.find((e) => e.kind === "planned") || {}
		return { name, title: shown.title || name, kind: finished ? "finished" : "planned", date: shown.date || null }
	})
}

/**
 * Whether a key press closes the side panel: Esc, unless a popover is open (it closes first) or
 * the key went to a field, where Esc means "leave the field" and must not discard what was typed.
 */
export function closesPanel(event, dialogOpen = false) {
	if (event?.key !== "Escape" || dialogOpen) return false
	return !event.target?.closest?.('input, textarea, select, [contenteditable=""], [contenteditable="true"]')
}
