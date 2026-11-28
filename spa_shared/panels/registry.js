// Panel registry for cockpit record pages (#1909, #1910, #1915).
//
// A panel is a block that belongs to a record: the description, the properties, the chat,
// checklists, the Phriend report, later notes. It is declared once; the record page lays the
// panels out as tiles (tiling.js, PanelLayout.vue), so a new block is one declaration instead of
// a layout edit, and a cockpit can hide or add panels in its config.js.
//
// Pure functions only: the vitest setup runs in node without Vue (personal_frontend/vitest.config.js).
// The declarations themselves, which import components, live in definitions.js.

import { DEFAULT_MIN } from "./tiling.js"

/**
 * A panel declaration, with the defaults filled in.
 *
 * @param {object} def
 * @param {string} def.id unique, short, stable: user layouts store it
 * @param {string} def.title English, translated where it is shown
 * @param {string|object} [def.icon] feather icon name, or a component
 * @param {string[]} def.doctypes record types the panel belongs to
 * @param {object} def.component Vue component of the panel body
 * @param {(ctx) => object} [def.props] props for the body, from { doctype, record, api }
 * @param {(record) => boolean} [def.when] show the panel for this record at all
 * @param {(record) => string} [def.summary] the rail's tooltip, when the body doesn't report one
 * @param {number} [def.minWidth] the tile is never narrower (the chat: 768, Raven's desktop layout)
 * @param {number} [def.minHeight] the tile is never lower
 * @param {{ near: string, side: string }} [def.place] where a panel goes that a stored layout
 *   doesn't know yet (e.g. added in a later release)
 * @param {boolean} [def.popout] may be popped out (#1912)
 * @param {boolean} [def.persistent] the body stays mounted when another record opens (it follows
 *   its props instead); for the chat, whose frame and teleport target must not be swapped
 * @param {boolean} [def.bare] the body brings its own padding and scrolling
 */
export function definePanel(def) {
	if (!def?.id) throw new Error("A panel needs an id")
	if (!Array.isArray(def.doctypes) || !def.doctypes.length) throw new Error(`Panel ${def.id} needs doctypes`)
	return {
		icon: "square",
		props: () => ({}),
		when: () => true,
		minWidth: DEFAULT_MIN.w,
		minHeight: DEFAULT_MIN.h,
		popout: true,
		persistent: false,
		bare: false,
		...def,
	}
}

/**
 * Apply a cockpit's override for one record type: { hide: [ids], add: [defs] }.
 * Returns a new list; ids the cockpit names but nobody declared are ignored.
 */
export function applyCockpitOverride(definitions, override) {
	if (!override) return [...definitions]
	const hidden = new Set(override.hide || [])
	const added = (override.add || []).map(definePanel)
	const byId = new Map()
	for (const def of [...definitions, ...added]) {
		if (!hidden.has(def.id)) byId.set(def.id, def)
	}
	return [...byId.values()]
}

/**
 * The panels a record has, in declaration order: of its record type, kept by the cockpit, and
 * whose `when` holds. A `when` that throws hides its panel instead of taking the page down.
 *
 * @param {object[]} definitions all declared panels (definePanel results)
 * @param {{ doctype: string, record: object, cockpitPanels?: object }} ctx
 */
export function panelsFor(definitions, { doctype, record, cockpitPanels } = {}) {
	if (!doctype || !record) return []
	const own = definitions.filter((d) => d.doctypes.includes(doctype))
	return applyCockpitOverride(own, cockpitPanels?.[doctype]).filter((d) => {
		try {
			return d.when(record)
		} catch (e) {
			return false
		}
	})
}

/** { id: { w, h } } for tiling.js. */
export function minimums(definitions) {
	return Object.fromEntries(definitions.map((d) => [d.id, { w: d.minWidth, h: d.minHeight }]))
}

/** { id: place } for tiling.withAll. */
export function places(definitions) {
	return Object.fromEntries(definitions.filter((d) => d.place).map((d) => [d.id, d.place]))
}
