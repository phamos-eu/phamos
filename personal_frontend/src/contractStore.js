// My Employment Contracts (#1600). Loaded once at start; the sidebar shows "My Contract"
// only when there is at least one submitted contract to show.
import { reactive } from "vue"
import { call } from "frappe-ui"
import spaConfig from "./config"

export const myContracts = reactive({ data: null, loaded: false, error: "" })

let inflight = null

export function loadMyContracts() {
	if (!inflight) {
		inflight = call(`${spaConfig.api}.get_my_contracts`)
			.then((data) => {
				myContracts.data = data
				myContracts.error = ""
			})
			.catch((e) => {
				myContracts.data = null
				myContracts.error = e?.message || "Could not load your contracts"
			})
			.finally(() => {
				myContracts.loaded = true
				inflight = null
			})
	}
	return inflight
}

export function hasContracts() {
	return Boolean(myContracts.data?.history?.length)
}
