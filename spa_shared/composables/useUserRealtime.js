import { getCurrentInstance, inject, onBeforeUnmount } from "vue"

/**
 * Listen to a realtime event Frappe publishes to the session user's own room
 * (frappe.publish_realtime(event, ..., user=...)). Calls `handler` debounced.
 * No-op without a socket. Unlike the site-wide `list_update`, these events only
 * reach the user they concern.
 */
export function useUserRealtime(event, handler, { debounceMs = 600 } = {}) {
	const instance = getCurrentInstance()
	const socket = instance?.appContext.config.globalProperties.$socket || inject("$socket", null)
	if (!socket?.on) return { available: false }

	let timer = null
	const listener = (payload) => {
		clearTimeout(timer)
		timer = setTimeout(() => handler(payload), debounceMs)
	}
	socket.on(event, listener)
	onBeforeUnmount(() => {
		clearTimeout(timer)
		socket.off?.(event, listener)
	})
	return { available: true }
}
