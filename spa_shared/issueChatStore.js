// Issue chat state shared across views (#1617): the list's chat icon asks the open Issue to show
// its chat drawer, and the chat button tells the lists when a chat was read or changed.
import { reactive } from "vue"

export const issueChatStore = reactive({
	/** Issue whose chat shows in the page (the dock's chat panel or the overlay) */
	openFor: null,
	/**
	 * The chat panel of the record page (#1911, #1915): { record, expanded, available }. The chat
	 * lays itself into that panel while it shows in a tile; the panel's rail icon opens it.
	 */
	dockHost: null,
	/** Asks the record page to open a panel: { record, panel } (the list's chat icon) */
	expandRequest: null,
	/**
	 * Per record, what the chat button knows, for the panel's rail icon:
	 * { enabled (undefined while loading), summary, badge, tone }
	 */
	chats: {},
	/** Issue name whose chat should open once that Issue is shown */
	openRequest: null,
	/** Where in that chat: { messageId, threadId } (either may be null) */
	openTarget: null,
	/** Bumped when a chat was opened, closed or started; lists reload their states */
	version: 0,
})

export function requestChatOpen(issueName, target = null) {
	issueChatStore.openTarget = target
	issueChatStore.openRequest = issueName
}

export function chatChanged() {
	issueChatStore.version++
}
