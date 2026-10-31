import { describe, expect, it } from "vitest"
import { countWords, htmlToPlainText, plainTextToHtml, wordGoal } from "./ideaText.js"

describe("ideaText", () => {
	it("flattens rich text to paragraphs", () => {
		expect(htmlToPlainText("<p>One <b>two</b></p><ul><li>three</li></ul><p>a<br>b</p>")).toBe(
			"One two\n\nthree\n\na\nb"
		)
		expect(htmlToPlainText("<p>5 &lt; 6 &amp;&nbsp;ok</p>")).toBe("5 < 6 & ok")
		expect(htmlToPlainText(null)).toBe("")
	})

	it("writes paragraphs and line breaks back, escaped", () => {
		expect(plainTextToHtml("One\ntwo\n\n<three>")).toBe("<p>One<br>two</p><p>&lt;three&gt;</p>")
		expect(plainTextToHtml("  ")).toBe("")
	})

	it("survives a round trip", () => {
		const text = "First paragraph\nwith a break\n\nSecond & last"
		expect(htmlToPlainText(plainTextToHtml(text))).toBe(text)
	})

	it("counts words", () => {
		expect(countWords("  one two\nthree, four. ")).toBe(4)
		expect(countWords("")).toBe(0)
	})

	it("derives the goal like the server", () => {
		expect(wordGoal(0, "similar")).toBe(300)
		expect(wordGoal(0, "less")).toBe(255)
		expect(wordGoal(420, "more")).toBe(483)
	})
})
