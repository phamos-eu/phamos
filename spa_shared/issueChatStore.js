// Issue chat state shared across views (#1617): the list's chat icon asks the open Issue to show
// its chat drawer, and the chat button tells the lists when a chat was read or changed.
import { reactive } from "vue"

export const issueChatStore = reactive({
	/** Issue whose chat is open; IssuesInbox shows the chat column for it */
	openFor: null,
	/** Issue name whose chat drawer should open once that Issue is shown */
	openRequest: null,
	/** Bumped when a chat was opened, closed or started; lists reload their states */
	version: 0,
})

export function requestChatOpen(issueName) {
	issueChatStore.openRequest = issueName
}

export function chatChanged() {
	issueChatStore.version++
}
