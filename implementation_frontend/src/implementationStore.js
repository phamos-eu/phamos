// The implementation open in the cockpit. App.vue loads it when the URL changes; the Overview
// and the sidebar contact read it.
import { reactive } from "vue"
import { call } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"
import spaConfig from "./config"

export const current = reactive({ name: null, data: null, loading: false, error: "" })

export function loadImplementation(name) {
	if (!name || (name === current.name && (current.data || current.loading))) return
	current.name = name
	current.data = null
	current.loading = true
	current.error = ""
	call(`${spaConfig.api}.get_overview`, { implementation: name })
		.then((data) => {
			if (current.name === name) current.data = data
		})
		.catch((e) => {
			if (current.name === name) current.error = e?.message || __("Could not load the implementation")
		})
		.finally(() => {
			if (current.name === name) current.loading = false
		})
}
