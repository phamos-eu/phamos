import { describe, expect, it } from "vitest"
import { handlePoint, linkTargetId } from "./ganttDependencyDrag.js"

const deps = { B: ["A"], C: [] }
const rows = {
	isLocked: (id) => id === "LOCKED",
	dependsOn: (id) => deps[id] || [],
}

describe("linkTargetId", () => {
	it("accepts another unlocked bar", () => {
		expect(linkTargetId("A", "C", rows)).toBe("C")
	})

	it("refuses no target, the bar itself and locked rows", () => {
		expect(linkTargetId("A", null, rows)).toBeNull()
		expect(linkTargetId("A", "A", rows)).toBeNull()
		expect(linkTargetId("A", "LOCKED", rows)).toBeNull()
	})

	it("refuses a link that exists already", () => {
		expect(linkTargetId("A", "B", rows)).toBeNull()
	})

	it("refuses the direct reverse of an existing link", () => {
		expect(linkTargetId("B", "A", rows)).toBeNull()
	})
})

describe("handlePoint", () => {
	it("sits right of the bar, vertically centred, relative to the origin", () => {
		const bar = { left: 150, right: 250, top: 120, height: 24 }
		const origin = { left: 100, top: 100 }
		expect(handlePoint(bar, origin)).toEqual({ x: 159, y: 32 })
	})
})
