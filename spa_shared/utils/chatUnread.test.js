import { describe, expect, it } from "vitest"
import { totalUnread, unreadSummary } from "./chatUnread.js"

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
