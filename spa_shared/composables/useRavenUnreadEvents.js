import { getCurrentInstance, inject, onBeforeUnmount } from "vue"

// Raven's unread events (#1618, #1623): new channel messages go to the room of everyone with the
// "Raven User" role (`doctype:Raven User`, raven/utils.py get_raven_room), new thread replies to
// the participant's own room. The cockpit joins the first one like Raven's own app does.
const EVENTS = [
	["raven:unread_channel_count_updated", "channel"],
	["raven:unread_thread_count_updated", "thread"],
]

/**
 * Call `handler` (debounced) when Raven reports new unread messages that concern the caller.
 * The channel room carries every channel's messages site-wide, so `concerns(event)` decides
 * per event ({ type: "channel" | "thread", channel_id, sent_by }) whether to reload at all.
 * No-op without a socket.
 */
export function useRavenUnreadEvents(handler, { debounceMs = 600, concerns = () => true } = {}) {
	const instance = getCurrentInstance()
	const socket = instance?.appContext.config.globalProperties.$socket || inject("$socket", null)
	if (!socket?.on) return { available: false }

	const subscribe = () => socket.emit("doctype_subscribe", "Raven User")
	let timer = null
	const listeners = EVENTS.map(([event, type]) => [
		event,
		(payload) => {
			if (!concerns({ type, channel_id: payload?.channel_id, sent_by: payload?.sent_by })) return
			clearTimeout(timer)
			timer = setTimeout(handler, debounceMs)
		},
	])
	subscribe()
	socket.on("connect", subscribe) // rooms do not survive a reconnect
	for (const [event, listener] of listeners) socket.on(event, listener)
	onBeforeUnmount(() => {
		clearTimeout(timer)
		socket.off?.("connect", subscribe)
		for (const [event, listener] of listeners) socket.off?.(event, listener)
	})
	return { available: true }
}
