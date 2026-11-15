// The user's panel layout (#1910): order, expanded/collapsed and dock width per record type.
//
// Booted with the page (spa_boot → preferences.cockpit_panel_layout), so the dock renders in its
// final shape without a request. Changes are saved as a user default, debounced, so dragging the
// splitter or clicking through panels sends one request, not dozens.

import { reactive } from "vue"
import { call } from "frappe-ui"

const KEY = "cockpit_panel_layout"
const SAVE_DELAY_MS = 800

function bootedLayout() {
	const value = typeof window !== "undefined" ? window.frappe?.boot?.preferences?.[KEY] : null
	return value && typeof value === "object" ? value : {}
}

// One store per page: every dock (and the gear menu) reads and writes the same object.
const layouts = reactive(bootedLayout())
let saveTimer = null

function scheduleSave() {
	clearTimeout(saveTimer)
	saveTimer = setTimeout(save, SAVE_DELAY_MS)
}

async function save() {
	saveTimer = null
	try {
		await call("phamos.api.cockpit_preferences.set_preference", {
			key: KEY,
			value: JSON.stringify(layouts),
		})
	} catch (e) {
		// The layout is a convenience: the page keeps working with the unsaved one.
		console.warn("Could not save the panel layout", e)
	}
}

// A layout still waiting for its debounce would be lost when the tab closes. A fetch is
// cancelled with the page, a beacon is not; Frappe reads the CSRF token from the form too.
if (typeof window !== "undefined") {
	window.addEventListener("pagehide", () => {
		if (!saveTimer) return
		clearTimeout(saveTimer)
		saveTimer = null
		const form = new FormData()
		form.append("key", KEY)
		form.append("value", JSON.stringify(layouts))
		if (window.csrf_token) form.append("csrf_token", window.csrf_token)
		navigator.sendBeacon?.("/api/method/phamos.api.cockpit_preferences.set_preference", form)
	})
}

export function usePanelLayout(doctype) {
	return {
		/** The stored layout of this record type ({} when none). */
		get() {
			return layouts[doctype] || {}
		},
		/** Replace the layout of this record type and save it. */
		set(next) {
			layouts[doctype] = next
			scheduleSave()
		},
		/** Forget the arrangement of this record type: back to the code defaults. */
		reset() {
			delete layouts[doctype]
			scheduleSave()
		},
	}
}
