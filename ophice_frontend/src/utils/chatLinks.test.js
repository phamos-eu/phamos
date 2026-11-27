import { describe, expect, it } from "vitest"
import { chatParts } from "./chatLinks.js"

// #2169: a link pasted into an Ophice chat was plain text; users had to copy and paste it.
describe("chatParts", () => {
	it("keeps a message without links as one text part", () => {
		expect(chatParts("hello there")).toEqual([{ text: "hello there" }])
	})

	it("returns no parts for an empty message", () => {
		expect(chatParts("")).toEqual([])
		expect(chatParts(undefined)).toEqual([])
	})

	it("turns an https address into a link", () => {
		expect(chatParts("see https://phamos.eu/app/issue/ISS-1 now")).toEqual([
			{ text: "see " },
			{ text: "https://phamos.eu/app/issue/ISS-1", href: "https://phamos.eu/app/issue/ISS-1" },
			{ text: " now" },
		])
	})

	it("turns an http address and a whole message link into links", () => {
		expect(chatParts("http://example.com")).toEqual([{ text: "http://example.com", href: "http://example.com" }])
	})

	it("adds https:// to www. addresses", () => {
		expect(chatParts("www.phamos.eu")).toEqual([{ text: "www.phamos.eu", href: "https://www.phamos.eu" }])
	})

	it("keeps query strings and fragments in the link", () => {
		const url = "https://meet.example.com/room?x=1&y=2#top"
		expect(chatParts(url)).toEqual([{ text: url, href: url }])
	})

	it("finds several links and keeps line breaks in the text", () => {
		const parts = chatParts("a https://a.example\nb https://b.example")
		expect(parts.filter((p) => p.href).map((p) => p.href)).toEqual(["https://a.example", "https://b.example"])
		expect(parts.map((p) => p.text).join("")).toBe("a https://a.example\nb https://b.example")
	})

	it("leaves sentence punctuation outside the link", () => {
		expect(chatParts("Look at https://phamos.eu.")).toEqual([
			{ text: "Look at " },
			{ text: "https://phamos.eu", href: "https://phamos.eu" },
			{ text: "." },
		])
		expect(chatParts("(see https://phamos.eu/a)")[1]).toEqual({ text: "https://phamos.eu/a", href: "https://phamos.eu/a" })
	})

	it("keeps a closing bracket that belongs to the address", () => {
		const url = "https://en.wikipedia.org/wiki/Frappe_(software)"
		expect(chatParts(url)).toEqual([{ text: url, href: url }])
	})

	it("does not link e-mail addresses, javascript: or bare prefixes", () => {
		expect(chatParts("mail info@www.phamos.eu")).toEqual([{ text: "mail info@www.phamos.eu" }])
		expect(chatParts("javascript:alert(1)")).toEqual([{ text: "javascript:alert(1)" }])
		expect(chatParts("type https:// and www. first")).toEqual([{ text: "type https:// and www. first" }])
	})

	it("keeps markup as text", () => {
		const parts = chatParts('<img src=x onerror="alert(1)"> https://phamos.eu')
		expect(parts[0]).toEqual({ text: '<img src=x onerror="alert(1)"> ' })
		expect(parts[1].href).toBe("https://phamos.eu")
	})
})
