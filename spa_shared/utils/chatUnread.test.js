import { describe, expect, it } from "vitest"
import { concernsChats, totalUnread, unreadSummary } from "./chatUnread.js"

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
