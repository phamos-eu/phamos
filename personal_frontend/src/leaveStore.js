// My Leave (#1714). Loaded once at start so the sidebar shows "My Leave" only for users with an
// active Employee record; the view reloads it after every change.
import { reactive } from "vue"
import { call } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"
import spaConfig from "./config"

export const myLeave = reactive({ data: null, balance: null, loaded: false, error: "" })

let inflight = null

export function loadMyLeave() {
	if (!inflight) {
		inflight = Promise.all([
			call(`${spaConfig.api}.get_my_leave`),
			call(`${spaConfig.api}.get_my_leave_balance`).catch(() => null),
		])
			.then(([data, balance]) => {
				myLeave.data = data
				myLeave.balance = balance
				myLeave.error = ""
			})
			.catch((e) => {
				myLeave.data = null
				myLeave.error = e?.message || __("Could not load your leave")
			})
			.finally(() => {
				myLeave.loaded = true
				inflight = null
			})
	}
	return inflight
}

export function hasLeaveAccess() {
	return Boolean(myLeave.data?.has_employee)
}
