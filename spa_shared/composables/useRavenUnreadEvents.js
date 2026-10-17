import { getCurrentInstance, inject, onBeforeUnmount } from "vue"

// Raven's unread events (#1618): new channel messages go to the room of everyone with the
// "Raven User" role (`doctype:Raven User`, raven/utils.py get_raven_room), new thread replies to
// the participant's own room. The cockpit joins the first one like Raven's own app does.
const EVENTS = ["raven:unread_channel_count_updated", "raven:unread_thread_count_updated"]

/**
 * Call `handler` (debounced) whenever Raven reports new unread messages somewhere. Cheap to use
 * from several components; each reloads only what it shows. No-op without a socket.
 */
export function useRavenUnreadEvents(handler, { debounceMs = 600 } = {}) {
	const instance = getCurrentInstance()
	const socket = instance?.appContext.config.globalProperties.$socket || inject("$socket", null)
	if (!socket?.on) return { available: false }

	const subscribe = () => socket.emit("doctype_subscribe", "Raven User")
	let timer = null
	const listener = () => {
		clearTimeout(timer)
		timer = setTimeout(handler, debounceMs)
	}
	subscribe()
	socket.on("connect", subscribe) // rooms do not survive a reconnect
	for (const event of EVENTS) socket.on(event, listener)
	onBeforeUnmount(() => {
		clearTimeout(timer)
		socket.off?.("connect", subscribe)
		for (const event of EVENTS) socket.off?.(event, listener)
	})
	return { available: true }
}
