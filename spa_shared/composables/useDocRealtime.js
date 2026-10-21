import { getCurrentInstance, onBeforeUnmount, ref, watch } from "vue"
import { call } from "frappe-ui"
import { sessionUser } from "@spa/session.js"

const PRESENCE_API = "phamos.api.presence"
const userCards = new Map()

async function resolveUsers(users) {
	const missing = users.filter((u) => !userCards.has(u))
	if (missing.length) {
		try {
			const cards = await call(`${PRESENCE_API}.get_user_cards`, { users: missing })
			for (const card of cards || []) userCards.set(card.name, card)
		} catch (e) {
			// Presence is decoration; fall back to bare user ids.
		}
	}
	return users.map((u) => userCards.get(u) || { name: u, full_name: u, user_image: "" })
}

/**
 * Follow one document over Frappe's socket.io realtime, which every cockpit
 * already connects to through the frappe-ui plugin (`$socket`).
 *
 * - `doc_update` (sent by Frappe after every save) → onDocUpdate(modified)
 * - `doc_viewers` → `viewers` (other users with the document open)
 * - `on(event, handler)` for custom events published to the document room
 *   with `frappe.publish_realtime(..., doctype=, docname=)`
 *
 * Without a socket (e.g. realtime not running) everything is a no-op.
 */
export function useDocRealtime({ doctype, name, onDocUpdate }) {
	const instance = getCurrentInstance()
	const socket = instance?.appContext?.config?.globalProperties?.$socket || null
	const viewers = ref([])
	const connected = ref(Boolean(socket?.connected))
	const listeners = []
	const reconnectHandlers = []
	let current = null

	function listen(event, handler) {
		if (!socket) return
		socket.on(event, handler)
		listeners.push([event, handler])
	}

	function open(docname) {
		socket.emit("doc_subscribe", doctype, docname)
		socket.emit("doc_open", doctype, docname)
	}

	function close(docname) {
		socket.emit("doc_unsubscribe", doctype, docname)
		socket.emit("doc_close", doctype, docname)
	}

	if (socket) {
		listen("doc_update", (data) => {
			if (data?.doctype === doctype && data?.name === current) onDocUpdate?.(String(data.modified || ""))
		})
		listen("doc_viewers", async (data) => {
			if (data?.doctype !== doctype || data?.docname !== current) return
			const me = sessionUser()
			const others = [...new Set(data.users || [])].filter((u) => u && u !== me)
			const docname = current
			const cards = await resolveUsers(others)
			if (docname === current) viewers.value = cards
		})
		listen("connect", () => {
			connected.value = true
			// Rooms do not survive a reconnect.
			if (current) open(current)
			for (const handler of reconnectHandlers) handler()
		})
		listen("disconnect", () => {
			connected.value = false
		})

		watch(
			name,
			(docname, previous) => {
				if (previous) close(previous)
				viewers.value = []
				current = docname || null
				if (current) open(current)
			},
			{ immediate: true }
		)
	}

	if (instance) {
		onBeforeUnmount(() => {
			if (!socket) return
			if (current) close(current)
			for (const [event, handler] of listeners) socket.off(event, handler)
		})
	}

	return {
		available: Boolean(socket),
		connected,
		viewers,
		/** Listen to a custom event published to this document's room. */
		on: (event, handler) => listen(event, handler),
		onReconnect: (handler) => reconnectHandlers.push(handler),
	}
}
