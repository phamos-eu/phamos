// Which Customers and Implementations the session user may open (#1671, picker #1672).
// Loaded once; the router and the sidebar picker read from it.
import { reactive } from "vue"
import { call } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"
import spaConfig from "./config"

export const scope = reactive({ loaded: false, isInternal: false, customers: [], error: "" })

let inflight = null

export function loadScope() {
	if (scope.loaded) return Promise.resolve(scope)
	if (!inflight) {
		inflight = call(`${spaConfig.api}.get_scope`)
			.then((data) => {
				scope.isInternal = Boolean(data?.is_internal)
				scope.customers = data?.customers || []
				scope.error = ""
			})
			.catch((e) => {
				scope.customers = []
				scope.error = e?.message || __("Could not load your implementations")
			})
			.finally(() => {
				scope.loaded = true
				inflight = null
			})
	}
	return inflight.then(() => scope)
}

export function allImplementations() {
	return scope.customers.flatMap((c) => c.implementations)
}

export function customerOf(implementation) {
	return scope.customers.find((c) => c.implementations.some((i) => i.name === implementation))
}

/** The implementation to open when the URL names none: the last one used, else the first. */
export function defaultImplementation() {
	const names = allImplementations().map((i) => i.name)
	let last = null
	try {
		last = localStorage.getItem(spaConfig.lastImplementationKey)
	} catch (e) {
		/* ignore */
	}
	return names.includes(last) ? last : names[0] || null
}

export function rememberImplementation(name) {
	try {
		localStorage.setItem(spaConfig.lastImplementationKey, name)
	} catch (e) {
		/* ignore */
	}
}
