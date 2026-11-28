import { onBeforeUnmount, onMounted, ref, unref, watch } from "vue"
import { call } from "frappe-ui"
import { issueChatStore } from "@spa/issueChatStore.js"
import { useRavenUnreadEvents } from "@spa/composables/useRavenUnreadEvents.js"
import { sessionUser } from "@spa/session.js"
import { concernsChats } from "@spa/utils/chatUnread.js"
import spaConfig from "@/config"

/**
 * Chat state per Issue for a list (#1617): { [name]: { channel_id, is_member, archived, unread,
 * unread_threads } },
 * only for Issues that have a chat. One call per list; reloads when the listed Issues change,
 * when a chat was read or changed (issueChatStore.version), when Raven reports new unread
 * messages or thread replies (#1618, #1623), and when the window gets focus again.
 * Empty when the Issue chat is off.
 * @param {import("vue").Ref<Array>|Array} issues
 */
export function useIssueChatStates(issues) {
	const states = ref({})
	let timer = null
	let request = 0

	function names() {
		return (unref(issues) || []).map((issue) => issue?.name).filter(Boolean)
	}

	async function load() {
		const list = names()
		const mine = ++request
		if (!list.length) {
			states.value = {}
			return
		}
		try {
			const result = await call(`${spaConfig.api}.get_issue_chat_states`, { names: JSON.stringify(list) })
			if (mine === request) states.value = result || {}
		} catch (e) {
			// The chat is an add-on; a list without its icons is still a list.
			if (mine === request) states.value = {}
		}
	}

	function schedule() {
		clearTimeout(timer)
		timer = setTimeout(load, 150)
	}

	watch(() => names().join("|"), schedule, { immediate: true })
	watch(() => issueChatStore.version, schedule)
	// Raven's channel events cover every channel on the site: reload only for the listed chats.
	useRavenUnreadEvents(schedule, {
		concerns: (event) =>
			concernsChats(event, new Set(Object.values(states.value).map((s) => s.channel_id)), sessionUser()),
	})
	onMounted(() => window.addEventListener("focus", schedule))
	onBeforeUnmount(() => {
		clearTimeout(timer)
		window.removeEventListener("focus", schedule)
	})

	return states
}
