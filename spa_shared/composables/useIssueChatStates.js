import { onBeforeUnmount, onMounted, ref, unref, watch } from "vue"
import { call } from "frappe-ui"
import { issueChatStore } from "@spa/issueChatStore.js"
import { useRavenUnreadEvents } from "@spa/composables/useRavenUnreadEvents.js"
import { sessionUser } from "@spa/session.js"
import { concernsChats } from "@spa/utils/chatUnread.js"
import spaConfig from "@/config"

// The server answers for at most 500 records per call (issue_chat.MAX_STATE_NAMES); a cockpit
// list can hold up to 1000 Issues, so larger lists ask in parts (#1797).
const STATES_PER_CALL = 500

/**
 * Chat state per Issue for a list (#1617): { [name]: { channel_id, is_member, archived, unread,
 * unread_threads } },
 * only for Issues that have a chat. One call per 500 Issues; reloads when the listed Issues change,
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
			const parts = []
			for (let i = 0; i < list.length; i += STATES_PER_CALL) parts.push(list.slice(i, i + STATES_PER_CALL))
			const results = await Promise.all(
				parts.map((names) => call(`${spaConfig.api}.get_issue_chat_states`, { names: JSON.stringify(names) }))
			)
			if (mine === request) states.value = Object.assign({}, ...results.map((r) => r || {}))
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
