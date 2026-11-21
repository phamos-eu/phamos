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
	it("attaches each emoji on its own side, never mirrored (PM, 2026-11-21)", () => {
		for (const [name, g] of Object.entries(GESTURES)) expect([undefined, "left", "right"], name).toContain(g.side)
		expect(GESTURES.muscle.side).toBe("left")
		expect(GESTURES.clap.side).toBe("left")
		expect(GESTURES.point.side).toBe("right")
		expect(ball_source).not.toMatch(/\.hand[^{]*\{[^}]*scale:\s*-1/)
	})
	it("gives every gesture an emoji and a motion that has its keyframe", () => {
		for (const [name, g] of Object.entries(GESTURES)) {
			expect(g.hand, name).toMatch(/\p{Extended_Pictographic}/u)
			if (g.motion === "still") continue
			expect(ball_source, `${name}: @keyframes hand-${g.motion}`).toContain(`@keyframes hand-${g.motion} `)
			expect(ball_source, `${name}: data-motion="${g.motion}"`).toContain(`data-motion="${g.motion}"`)
		}
	})
})
