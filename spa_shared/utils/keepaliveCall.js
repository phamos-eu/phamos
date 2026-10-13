import { call } from "frappe-ui"

// Browsers cap keepalive request bodies at 64 KiB in total.
const KEEPALIVE_LIMIT = 60000

/**
 * POST a whitelisted method so that it survives the page being closed
 * (pagehide). Same headers as frappe-ui `call`; the response is ignored.
 * Larger bodies fall back to a normal call, which may be cut off on close.
 */
export function callKeepalive(method, args = {}) {
	const body = JSON.stringify(args)
	if (body.length > KEEPALIVE_LIMIT || typeof fetch !== "function") {
		return call(method, args).catch(() => {})
	}
	const headers = {
		Accept: "application/json",
		"Content-Type": "application/json; charset=utf-8",
		"X-Frappe-Site-Name": window.location.hostname,
	}
	if (window.csrf_token && window.csrf_token !== "{{ csrf_token }}") {
		headers["X-Frappe-CSRF-Token"] = window.csrf_token
	}
	try {
		return fetch(`/api/method/${method}`, {
			method: "POST",
			headers,
			body,
			keepalive: true,
			credentials: "same-origin",
		}).catch(() => {})
	} catch (e) {
		return Promise.resolve()
	}
}
