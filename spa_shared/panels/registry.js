// Panel registry for the dock on cockpit record pages (#1909, #1910).
//
// A panel is a block that belongs to a record (checklists, the Phriend report, later chat and
// notes). It is declared once and the record page only renders the dock, so a new block is one
// declaration instead of a layout edit, and a cockpit can hide or reorder panels in its config.js.
//
// Pure functions only: the vitest setup runs in node without Vue (personal_frontend/vitest.config.js).
// The declarations themselves, which import components, live in definitions.js.

/** Width of the dock when no open panel asks for more. Matches the old w-80 checklist column. */
export const DEFAULT_DOCK_WIDTH = 320
export const MIN_DOCK_WIDTH = 240
export const MAX_DOCK_WIDTH = 1600

/**
 * A panel declaration, with the defaults filled in.
 *
 * @param {object} def
 * @param {string} def.id unique, short, stable: user layouts store it
 * @param {string} def.title English, translated where it is shown
 * @param {string} [def.icon] feather icon name
 * @param {string[]} def.doctypes record types the panel belongs to
 * @param {object} def.component Vue component of the panel body
 * @param {(ctx) => object} [def.props] props for the body, from { doctype, record, api }
 * @param {(record) => boolean} [def.when] show the panel for this record at all
 * @param {(record) => boolean} [def.defaultOpen] expanded until the user collapses it
 * @param {number} [def.minWidth] the dock is at least this wide while the panel is expanded
 * @param {boolean} [def.popout] may be popped out (#1912)
 * @param {boolean} [def.persistent] the body stays mounted when another record opens (it follows
 *   its props instead); for the chat, whose frame and teleport target must not be swapped
 * @param {boolean} [def.fill] while expanded it takes the dock's remaining height, without padding,
 *   and the dock stops scrolling (the Raven frame is laid over the page and can't be clipped)
 * @param {number} [def.order] position when neither cockpit nor user ordered it
 */
export function definePanel(def) {
	if (!def?.id) throw new Error("A panel needs an id")
	if (!Array.isArray(def.doctypes) || !def.doctypes.length) throw new Error(`Panel ${def.id} needs doctypes`)
	return {
		icon: "square",
		props: () => ({}),
		when: () => true,
		defaultOpen: () => true,
		minWidth: 0,
		popout: true,
		fill: false,
		persistent: false,
		order: 100,
		...def,
	}
}

/**
 * Apply a cockpit's override for one record type: { hide: [ids], order: [ids], add: [defs] }.
 * Returns a new list; ids the cockpit names but nobody declared are ignored.
 */
export function applyCockpitOverride(definitions, override) {
	if (!override) return sortByIds(definitions, [])
	const hidden = new Set(override.hide || [])
	const added = (override.add || []).map(definePanel)
	const byId = new Map()
	for (const def of [...definitions, ...added]) {
		if (!hidden.has(def.id)) byId.set(def.id, def)
	}
	return sortByIds([...byId.values()], override.order)
}

/** Ids listed in `ids` first, in that order; the rest after them, by their `order` then id. */
function sortByIds(defs, ids) {
	const rank = new Map((ids || []).map((id, i) => [id, i]))
	return [...defs].sort((a, b) => {
		const ra = rank.has(a.id) ? rank.get(a.id) : Infinity
		const rb = rank.has(b.id) ? rank.get(b.id) : Infinity
		if (ra !== rb) return ra - rb
		if (a.order !== b.order) return a.order - b.order
		return a.id.localeCompare(b.id)
	})
}

/**
 * The user's order applied to the panels it names; the others keep their place. So a panel added
 * later (e.g. the chat, #1911) appears where it was declared, not after everything the user ever
 * ordered.
 */
function reorderNamed(defs, ids) {
	const named = new Set(ids)
	const slots = []
	defs.forEach((def, index) => named.has(def.id) && slots.push(index))
	const moved = sortByIds(
		defs.filter((def) => named.has(def.id)),
		ids
	)
	const result = [...defs]
	slots.forEach((slot, i) => (result[slot] = moved[i]))
	return result
}

/**
 * The panels to show for one record, in order, each with whether it is expanded.
 *
 * Order: the user's stored order, then the cockpit's, then the declarations' own.
 * Expanded: collapsed only if the user collapsed it, else the panel's defaultOpen(record).
 *
 * @param {object[]} definitions all declared panels (definePanel results)
 * @param {object} ctx
 * @param {string} ctx.doctype
 * @param {object} ctx.record
 * @param {object} [ctx.cockpitPanels] the cockpit config's `panels` ({ [doctype]: override })
 * @param {object} [ctx.layout] the user's layout for this doctype ({ order, collapsed, expanded })
 * @returns {{ def, expanded: boolean, defaultExpanded: boolean }[]}
 */
export function panelsFor(definitions, { doctype, record, cockpitPanels, layout } = {}) {
	if (!doctype || !record) return []
	const own = definitions.filter((d) => d.doctypes.includes(doctype))
	const forCockpit = applyCockpitOverride(own, cockpitPanels?.[doctype])
	const visible = forCockpit.filter((d) => {
		try {
			return d.when(record)
		} catch (e) {
			// a broken condition hides its panel instead of taking the record page down
			return false
		}
	})
	const ordered = layout?.order?.length ? reorderNamed(visible, layout.order) : visible
	const collapsed = new Set(layout?.collapsed || [])
	const expanded = new Set(layout?.expanded || [])
	return ordered.map((def) => {
		const defaultExpanded = safeDefaultOpen(def, record)
		return {
			def,
			defaultExpanded,
			expanded: collapsed.has(def.id) ? false : expanded.has(def.id) || defaultExpanded,
		}
	})
}

function safeDefaultOpen(def, record) {
	try {
		return !!def.defaultOpen(record)
	} catch (e) {
		return false
	}
}

/**
 * How wide the dock is: the user's width, but never narrower than an expanded panel needs.
 * A panel that needs 768px (the Raven chat, #1911) widens the dock only while it is expanded.
 */
export function dockWidth(panels, userWidth) {
	const need = panels.filter((p) => p.expanded).reduce((max, p) => Math.max(max, p.def.minWidth || 0), 0)
	const want = Number.isFinite(userWidth) ? userWidth : DEFAULT_DOCK_WIDTH
	return clamp(Math.max(want, need), MIN_DOCK_WIDTH, MAX_DOCK_WIDTH)
}

export function clamp(value, min, max) {
	return Math.min(Math.max(value, min), max)
}

/**
 * The user's layout after expanding or collapsing one panel.
 * Only the deviation from the default is kept in `collapsed` / `expanded`, so a panel whose
 * default changes later (e.g. a checklist gets completed) follows the new default.
 */
export function toggled(layout, panelId, expand, defaultOpen) {
	const next = { ...(layout || {}) }
	const collapsed = new Set(next.collapsed || [])
	const expanded = new Set(next.expanded || [])
	collapsed.delete(panelId)
	expanded.delete(panelId)
	if (expand && !defaultOpen) expanded.add(panelId)
	if (!expand && defaultOpen) collapsed.add(panelId)
	next.collapsed = [...collapsed]
	next.expanded = [...expanded]
	return next
}

/** The user's layout after moving one panel up (-1) or down (+1) among those shown. */
export function moved(layout, shownIds, panelId, step) {
	const ids = [...shownIds]
	const from = ids.indexOf(panelId)
	const to = from + step
	if (from < 0 || to < 0 || to >= ids.length) return layout || {}
	ids.splice(from, 1)
	ids.splice(to, 0, panelId)
	// keep ids of panels not shown on this record (another Issue may show them) after these
	const rest = (layout?.order || []).filter((id) => !ids.includes(id))
	return { ...(layout || {}), order: [...ids, ...rest] }
}
