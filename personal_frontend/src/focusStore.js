// The user's running focus session (#1556), shared by the router guard, the shell and the
// focus view. Loaded once at start and refreshed on `cockpit_focus_changed`.
import { reactive } from "vue"
import { call } from "frappe-ui"
import spaConfig from "./config"

export const focus = reactive({ session: null, loaded: false, loadedAt: 0 })

let pending = null

export function setFocus(session) {
	focus.session = session && session.status === "Active" ? session : null
	focus.loaded = true
	focus.loadedAt = Date.now()
}

export async function loadFocus() {
	if (!pending) {
		pending = call(`${spaConfig.api}.get_active_focus`)
			.then(setFocus)
			.catch(() => setFocus(null)) // never lock the cockpit because the check failed
			.finally(() => (pending = null))
	}
	return pending
}

export async function ensureFocusLoaded() {
	if (!focus.loaded) await loadFocus()
	return focus.session
}
