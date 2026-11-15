import { dragOffsets, dropIndex, moved, passedDragDistance } from "./listReorder.js"

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

describe("dragOffsets", () => {
	it("moves the passed items up one slot when dragging down", () => {
		expect(dragOffsets(4, 0, 2, 50)).toEqual([0, -50, -50, 0])
	})
	it("moves the passed items down one slot when dragging up", () => {
		expect(dragOffsets(4, 3, 1, 50)).toEqual([0, 50, 50, 0])
	})
	it("moves nothing while the item is over its own slot", () => {
		expect(dragOffsets(3, 1, 1, 50)).toEqual([0, 0, 0])
	})
})

describe("passedDragDistance", () => {
	it("keeps a press that hardly moves a click", () => {
		expect(passedDragDistance(2, 2)).toBe(false)
	})
	it("starts a drag after a few pixels", () => {
		expect(passedDragDistance(0, 5)).toBe(true)
		expect(passedDragDistance(-3, -3)).toBe(true)
	})
})
