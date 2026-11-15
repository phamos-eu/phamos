// Issue chat state shared across views (#1617): the list's chat icon asks the open Issue to show
// its chat drawer, and the chat button tells the lists when a chat was read or changed.
import { reactive } from "vue"

export const issueChatStore = reactive({
	/** Issue whose chat shows in the page (the dock's chat panel or the overlay) */
	openFor: null,
	/**
	 * The chat panel of the dock (#1911): { record, expanded, available }. The chat lays itself into
	 * that panel while it is expanded and available; otherwise the chat button opens the overlay
	 * or, where the panel is available but collapsed, asks the dock to expand it.
	 */
	dockHost: null,
	/** Asks the dock to expand a panel: { record, panel } */
	expandRequest: null,
	/** Per record, what the chat button knows, for the dock row: { enabled, summary } */
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
