// Unread counts of an Issue chat for badges (#1617, #1623): the chat itself plus the replies in
// its threads the user takes part in (Raven shows those only on its Threads page).
import { __ } from "./i18n.js"

export function totalUnread(state) {
	return (state?.unread || 0) + (state?.unread_threads || 0)
}

/** "2 unread in the chat · 1 new reply in threads", or "" when nothing is unread. */
export function unreadSummary(state) {
	const parts = []
	const chat = state?.unread || 0
	const threads = state?.unread_threads || 0
	if (chat === 1) parts.push(__("1 unread in the chat"))
	else if (chat) parts.push(__("{0} unread in the chat", [chat]))
	if (threads === 1) parts.push(__("1 new reply in threads"))
	else if (threads) parts.push(__("{0} new replies in threads", [threads]))
	return parts.join(" · ")
}
