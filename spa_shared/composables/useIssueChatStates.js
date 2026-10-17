import { onBeforeUnmount, onMounted, ref, unref, watch } from "vue"
import { call } from "frappe-ui"
import { issueChatStore } from "@spa/issueChatStore.js"
import { useUserRealtime } from "@spa/composables/useUserRealtime.js"
import spaConfig from "@/config"

/**
 * Chat state per Issue for a list (#1617): { [name]: { channel_id, is_member, archived, unread,
 * unread_threads } },
 * only for Issues that have a chat. One call per list; reloads when the listed Issues change,
 * when a chat was read or changed (issueChatStore.version), when Raven reports a new thread reply
 * for the user (#1623), and when the window gets focus again.
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
	useUserRealtime("raven:unread_thread_count_updated", schedule)
	onMounted(() => window.addEventListener("focus", schedule))
	onBeforeUnmount(() => {
		clearTimeout(timer)
		window.removeEventListener("focus", schedule)
	})

	return states
}
