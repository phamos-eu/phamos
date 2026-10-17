import { ref } from "vue"
import { call } from "frappe-ui"
import { CONTRACTS_API } from "./contractFormat.js"

// Loaded once per page: the Contracts section is only for users who may read Employment Contracts.
const access = ref({ can_read: false, can_create: false, loaded: false })
let pending = null

export function useContractAccess() {
	if (!pending) {
		pending = call(`${CONTRACTS_API}.get_access`)
			.then((result) => (access.value = { ...result, loaded: true }))
			.catch(() => (access.value = { can_read: false, can_create: false, loaded: true }))
	}
	return { access, ready: pending }
}
