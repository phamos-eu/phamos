// Issue chat state shared across views (#1617): the list's chat icon asks the open Issue to show
// its chat drawer, and the chat button tells the lists when a chat was read or changed.
import { reactive } from "vue"

export const issueChatStore = reactive({
	/** Issue whose chat is open; IssuesInbox shows the chat column for it */
	openFor: null,
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
