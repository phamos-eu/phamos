import { readFileSync } from "node:fs"
import { describe, expect, it } from "vitest"
import { GESTURES } from "./ball.js"

const ball_source = readFileSync(new URL("./ball.js", import.meta.url), "utf8")

describe("GESTURES (#1990, #2009)", () => {
	it("has the bubble hands and the reactions of the companion", () => {
		for (const name of ["wave", "thumbs_up", "fingers_crossed", "wait", "point_up", "point",
			"thumbs_down", "thanks", "praise", "high_five", "clap", "heart", "star", "alert"])
			expect(GESTURES[name], name).toBeTruthy()
	})
	it("shows the emoji inside the bubble, not beside Phriend (PM, 2026-11-21)", () => {
		expect(ball_source).not.toContain('class="hand"')
		for (const g of Object.values(GESTURES)) expect(g.side).toBeUndefined()
	})
	it("gives every gesture an emoji and a motion that has its keyframe", () => {
		for (const [name, g] of Object.entries(GESTURES)) {
			expect(g.hand, name).toMatch(/\p{Extended_Pictographic}/u)
			if (g.motion === "still") continue
			expect(ball_source, `${name}: @keyframes hand-${g.motion}`).toContain(`@keyframes hand-${g.motion} `)
			expect(ball_source, `${name}: .emoji[data-motion="${g.motion}"]`).toContain(`.emoji[data-motion="${g.motion}"]`)
		}
	})
})
