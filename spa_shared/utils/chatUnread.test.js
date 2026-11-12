import { describe, expect, it } from "vitest"
import { compareChatStates, concernsChats, messageAge, totalUnread, unreadSummary, unreadTone } from "./chatUnread.js"

describe("chat unread counts", () => {
	it("adds thread replies to the chat count", () => {
		expect(totalUnread({ unread: 2, unread_threads: 3 })).toBe(5)
		expect(totalUnread({ unread: 0 })).toBe(0)
		expect(totalUnread(null)).toBe(0)
	})

	it("says where the unread messages are", () => {
		expect(unreadSummary({ unread: 2, unread_threads: 1 })).toBe("2 unread in the chat · 1 new reply in threads")
		expect(unreadSummary({ unread: 1, unread_threads: 0 })).toBe("1 unread in the chat")
		expect(unreadSummary({ unread: 0, unread_threads: 4 })).toBe("4 new replies in threads")
		expect(unreadSummary({})).toBe("")
	})
})

describe("chat badge tone (#1781)", () => {
	it("is blue for new messages and red only for a mention", () => {
		expect(unreadTone(null)).toBe("")
		expect(unreadTone({ unread: 0, unread_threads: 0, mentions: 0 })).toBe("")
		expect(unreadTone({ unread: 2 })).toBe("new")
		expect(unreadTone({ unread_threads: 1, mentions: 0 })).toBe("new")
		expect(unreadTone({ unread: 1, mentions: 1 })).toBe("mention")
	})

	it("says so when the user was mentioned", () => {
		expect(unreadSummary({ unread: 1, mentions: 1 })).toBe("You were mentioned · 1 unread in the chat")
	})
})

describe("Raven events that concern a list", () => {
	const mine = new Set(["issues-issue-iss-1", "issues-issue-iss-2"])

	it("reloads for messages in the listed chats", () => {
		expect(concernsChats({ type: "channel", channel_id: "issues-issue-iss-1", sent_by: "b@x" }, mine, "a@x")).toBe(true)
	})

	it("ignores other channels and our own messages", () => {
		expect(concernsChats({ type: "channel", channel_id: "general", sent_by: "b@x" }, mine, "a@x")).toBe(false)
		expect(concernsChats({ type: "channel", channel_id: "issues-issue-iss-1", sent_by: "a@x" }, mine, "a@x")).toBe(false)
		expect(concernsChats({ type: "channel", sent_by: "b@x" }, mine, "a@x")).toBe(false)
		expect(concernsChats(null, mine, "a@x")).toBe(false)
	})

	it("always reloads for thread replies, which only reach their participants", () => {
		expect(concernsChats({ type: "thread", channel_id: "tlj581p2hq", sent_by: "b@x" }, mine, "a@x")).toBe(true)
		expect(concernsChats({ type: "thread", channel_id: "tlj581p2hq", sent_by: "a@x" }, mine, "a@x")).toBe(false)
	})
})

describe("sorting by chat (#1796)", () => {
	const none = undefined
	const read = { unread: 0, last_message_at: "2026-11-01 10:00:00" }
	const readLater = { unread: 0, last_message_at: "2026-11-01 12:00:00" }
	const fresh = { unread: 2, last_message_at: "2026-10-01 09:00:00" }
	const thread = { unread: 0, unread_threads: 1, last_message_at: "2026-10-02 09:00:00" }
	const mention = { unread: 1, mentions: 1, last_message_at: "2026-09-01 09:00:00" }

	it("puts mentions first, then unread, then read chats, then no chat", () => {
		const sorted = [read, none, mention, fresh, readLater, thread].sort((a, b) => -compareChatStates(a, b))
		expect(sorted).toEqual([mention, fresh, thread, readLater, read, none])
	})

	it("puts more unread messages first, then the latest message", () => {
		const many = { unread: 5, last_message_at: "2026-09-01 09:00:00" }
		const manyMentions = { unread: 4, mentions: 1, last_message_at: "2026-08-01 09:00:00" }
		const sorted = [fresh, many, thread, mention, manyMentions].sort((a, b) => -compareChatStates(a, b))
		expect(sorted).toEqual([manyMentions, mention, many, fresh, thread])
	})

	it("treats equal states as equal", () => {
		expect(compareChatStates(none, none)).toBe(0)
		expect(compareChatStates(read, { ...read })).toBe(0)
	})
})

describe("last message age (#1796)", () => {
	it("is short and grows in steps", () => {
		expect(messageAge(null)).toBe("")
		expect(messageAge(30)).toBe("just now")
		expect(messageAge(5 * 60)).toBe("5 min ago")
		expect(messageAge(3 * 3600 + 59)).toBe("3 h ago")
		expect(messageAge(2 * 86400)).toBe("2 d ago")
		expect(messageAge(15 * 86400)).toBe("2 wk ago")
		expect(messageAge(65 * 86400)).toBe("2 mo ago")
		expect(messageAge(400 * 86400)).toBe("1 yr ago")
	})
})
