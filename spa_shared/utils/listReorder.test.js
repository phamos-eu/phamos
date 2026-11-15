import { dropIndex, moved } from "./listReorder.js"

const rects = [0, 50, 100, 150].map((top) => ({ top, height: 40 }))

describe("dropIndex", () => {
	it("counts the other items whose middle is above the pointer", () => {
		expect(dropIndex(5, rects, 3)).toBe(0) // dragged to the top
		expect(dropIndex(75, rects, 0)).toBe(1) // past item 1's middle (70)
		expect(dropIndex(65, rects, 0)).toBe(0) // not yet past it
		expect(dropIndex(500, rects, 0)).toBe(3) // to the end
		expect(dropIndex(130, rects, 2)).toBe(2) // over its own place
	})
})

describe("moved", () => {
	it("moves an item and leaves the original alone", () => {
		const list = ["a", "b", "c", "d"]
		expect(moved(list, 3, 1)).toEqual(["a", "d", "b", "c"])
		expect(moved(list, 0, 3)).toEqual(["b", "c", "d", "a"])
		expect(list).toEqual(["a", "b", "c", "d"])
	})
	it("ignores positions outside the list", () => {
		expect(moved(["a", "b"], 0, 5)).toEqual(["a", "b"])
	})
})
