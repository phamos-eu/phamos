// Unread counts of an Issue chat for badges (#1617, #1623): the chat itself plus the replies in
// its threads the user takes part in (Raven shows those only on its Threads page).
import { __ } from "./i18n.js"

export function totalUnread(state) {
	return (state?.unread || 0) + (state?.unread_threads || 0)
}

/**
 * How a chat badge looks (#1781): "mention" (red) when an unread message mentions the user,
 * "new" (blue, like Raven's "New messages") for anything else unread, "" when all is read.
 */
export function unreadTone(state) {
	if (!totalUnread(state)) return ""
	return state?.mentions ? "mention" : "new"
}

/** "2 unread in the chat · 1 new reply in threads", or "" when nothing is unread. */
export function unreadSummary(state) {
	const parts = []
	const mentions = state?.mentions || 0
	if (mentions === 1) parts.push(__("You were mentioned"))
	else if (mentions) parts.push(__("You were mentioned {0} times", [mentions]))
	const chat = state?.unread || 0
	const threads = state?.unread_threads || 0
	if (chat === 1) parts.push(__("1 unread in the chat"))
	else if (chat) parts.push(__("{0} unread in the chat", [chat]))
	if (threads === 1) parts.push(__("1 new reply in threads"))
	else if (threads) parts.push(__("{0} new replies in threads", [threads]))
	return parts.join(" · ")
}

/**
 * Whether one of Raven's unread events ({ type, channel_id, sent_by }) concerns chats we show:
 * not our own message, and a thread reply (Raven sends those only to the participants) or a
 * message in one of `channelIds`.
 */
export function concernsChats(event, channelIds, me) {
	if (!event || (me && event.sent_by === me)) return false
	if (event.type === "thread") return true
	return Boolean(event.channel_id) && channelIds.has(event.channel_id)
}

/** How urgent a chat is for sorting: 3 mention, 2 other unread, 1 all read, 0 no chat. */
function chatRank(state) {
	if (!state) return 0
	const tone = unreadTone(state)
	if (tone === "mention") return 3
	return tone ? 2 : 1
}

/**
 * Sorts list rows by their chat state (#1796), least urgent first (reverse it for "most urgent
 * first"): no chat, then read chats, then unread, then a mention. Within the same rank, more
 * unread messages are more urgent; then the latest message decides.
 */
export function compareChatStates(a, b) {
	const rank = chatRank(a) - chatRank(b)
	if (rank) return rank
	const unread = totalUnread(a) - totalUnread(b)
	if (unread) return unread
	return String(a?.last_message_at || "").localeCompare(String(b?.last_message_at || ""))
}
