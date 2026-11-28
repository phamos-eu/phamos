// My Leave (#1714). The list loads once at start so the sidebar shows "My Leave" only for users
// with an active Employee record; the view reloads list and balance after every change.
import { reactive } from "vue"
import { call } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"
import spaConfig from "./config"

export const myLeave = reactive({ data: null, balance: null, loaded: false, error: "" })

let inflight = null

// The list: enough for the sidebar ("has an Employee") and the view.
export function loadMyLeave() {
	if (!inflight) {
		inflight = call(`${spaConfig.api}.get_my_leave`)
			.then((data) => {
				myLeave.data = data
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

// The balance runs HRMS's leave ledger queries, so only the My Leave view asks for it.
export function loadMyLeaveBalance() {
	return call(`${spaConfig.api}.get_my_leave_balance`)
		.then((balance) => (myLeave.balance = balance))
		.catch(() => (myLeave.balance = null))
}

export function hasLeaveAccess() {
	return Boolean(myLeave.data?.has_employee)
}
