import { describe, expect, it } from "vitest"
import { useMapCamera } from "./useMapCamera.js"

// The view is 400×400 px at the page's top left; the grid 20×20 tiles, so 20 px a tile at zoom 1.
const box = { getBoundingClientRect: () => ({ left: 0, top: 0 }), setPointerCapture() {} }

function camera() {
	const cam = useMapCamera({ view: { width: 400, height: 400 }, grid: () => ({ cols: 20, rows: 20 }), image: () => null, storageKey: "test", pad: 0 })
	cam.place()
	return cam
}

const touch = (id, x, y) => ({ pointerId: id, pointerType: "touch", button: 0, clientX: x, clientY: y, currentTarget: box })

describe("Ophice map pinch zoom (#2213)", () => {
	it("zooms in when two fingers move apart, around the point between them", () => {
		// Zoomed in a little first, so the map has room to move under the fingers.
		const cam = camera()
		cam.setZoom(1.5)
		const before = cam.toView(10, 10)
		cam.onPointerDown(touch(1, 150, 200))
		cam.onPointerDown(touch(2, 250, 200))
		cam.onPointerMove(touch(1, 100, 200))
		cam.onPointerMove(touch(2, 300, 200))
		expect(cam.zoom.value).toBe(3)
		// The grid point under the fingers' middle stays under it.
		const after = cam.toView(10, 10)
		expect(after.x).toBeCloseTo(before.x)
		expect(after.y).toBeCloseTo(before.y)
		expect(cam.dragging.value).toBe(true)
	})

	it("zooms out when the fingers move together", () => {
		const cam = camera()
		cam.setZoom(2)
		cam.onPointerDown(touch(1, 100, 200))
		cam.onPointerDown(touch(2, 300, 200))
		cam.onPointerMove(touch(2, 200, 200))
		expect(cam.zoom.value).toBe(1)
	})

	it("goes on as a one-finger drag when a finger lifts, without a jump", () => {
		const cam = camera()
		cam.onPointerDown(touch(1, 150, 200))
		cam.onPointerDown(touch(2, 250, 200))
		cam.onPointerMove(touch(1, 100, 200))
		cam.onPointerMove(touch(2, 300, 200))
		cam.onPointerUp(touch(2, 300, 200))
		const pan = { ...cam.pan }
		expect(cam.dragging.value).toBe(true)
		cam.onPointerMove(touch(1, 80, 190))
		expect(cam.pan.x).toBeCloseTo(pan.x - 20)
		expect(cam.pan.y).toBeCloseTo(pan.y - 10)
		cam.onPointerUp(touch(1, 80, 190))
		expect(cam.dragging.value).toBe(false)
	})

	it("swallows the click that ends a pinch", () => {
		const cam = camera()
		cam.onPointerDown(touch(1, 150, 200))
		cam.onPointerDown(touch(2, 250, 200))
		cam.onPointerUp(touch(1, 150, 200))
		cam.onPointerUp(touch(2, 250, 200))
		let stopped = false
		cam.onClickCapture({ stopPropagation: () => (stopped = true), preventDefault() {} })
		expect(stopped).toBe(true)
	})

	it("still pans with one mouse drag", () => {
		const cam = camera()
		cam.setZoom(2)
		const pan = { ...cam.pan }
		const mouse = (x, y) => ({ pointerId: 1, pointerType: "mouse", button: 0, clientX: x, clientY: y, currentTarget: box })
		cam.onPointerDown(mouse(200, 200))
		cam.onPointerMove(mouse(230, 220))
		expect(cam.pan.x).toBeCloseTo(pan.x + 30)
		expect(cam.pan.y).toBeCloseTo(pan.y + 20)
		cam.onPointerUp(mouse(230, 220))
		expect(cam.dragging.value).toBe(false)
	})
})

describe("Ophice map pinch with more fingers and chips (#2213 review)", () => {
	it("ignores a third finger, and lifting it changes nothing", () => {
		const cam = camera()
		cam.setZoom(1.5)
		cam.onPointerDown({ ...touch(1, 150, 200), isPrimary: true })
		cam.onPointerDown(touch(2, 250, 200))
		cam.onPointerDown(touch(3, 50, 50))
		cam.onPointerMove(touch(3, 10, 10))
		expect(cam.zoom.value).toBe(1.5)
		cam.onPointerUp(touch(3, 10, 10))
		cam.onPointerMove(touch(2, 350, 200))
		expect(cam.zoom.value).toBe(3)
	})

	it("ends the drag when the last pinch finger lifts, even with a third finger still down", () => {
		const cam = camera()
		cam.onPointerDown({ ...touch(1, 150, 200), isPrimary: true })
		cam.onPointerDown(touch(2, 250, 200))
		cam.onPointerDown(touch(3, 50, 50))
		cam.onPointerUp(touch(2, 250, 200))
		cam.onPointerUp(touch(1, 150, 200))
		expect(cam.dragging.value).toBe(false)
	})

	it("pinches with a first finger noted on a chip; that finger alone does not pan", () => {
		const cam = camera()
		cam.setZoom(1.5)
		const pan = { ...cam.pan }
		cam.onPointerDown({ ...touch(1, 150, 200), isPrimary: true }, { pan: false })
		cam.onPointerMove(touch(1, 120, 200))
		expect(cam.pan).toEqual(pan)
		cam.onPointerUp(touch(1, 120, 200))
		expect(cam.dragging.value).toBe(false)
		cam.onPointerDown({ ...touch(1, 150, 200), isPrimary: true }, { pan: false })
		cam.onPointerDown(touch(2, 250, 200))
		cam.onPointerMove(touch(2, 300, 200))
		expect(cam.zoom.value).toBe(2.25)
	})

	it("drops a touch that never ended when a new gesture starts", () => {
		const cam = camera()
		cam.onPointerDown({ ...touch(1, 150, 200), isPrimary: true })
		// no pointerup or pointercancel for finger 1
		cam.onPointerDown({ ...touch(5, 100, 100), isPrimary: true })
		expect(cam.isPressed()).toBe(true)
		cam.onPointerUp(touch(5, 100, 100))
		expect(cam.isPressed()).toBe(false)
	})
})

describe("Ophice map: a touch on a chip (#2213, review of !1372)", () => {
	it("never pans from a chip on a primary touch, even after a touch that never ended", () => {
		const cam = camera()
		cam.setZoom(1.5)
		// An earlier touch on a chip lost its pointerup (the chip opened a menu).
		cam.onChipPointerDown({ ...touch(1, 150, 200), isPrimary: true })
		const pan = { ...cam.pan }
		cam.onChipPointerDown({ ...touch(2, 150, 200), isPrimary: true })
		cam.onPointerMove(touch(2, 100, 150))
		expect(cam.pan).toEqual(pan)
		expect(cam.dragging.value).toBe(false)
	})

	it("joins a pinch as the second finger", () => {
		const cam = camera()
		cam.setZoom(1.5)
		cam.onPointerDown({ ...touch(1, 150, 200), isPrimary: true })
		cam.onChipPointerDown({ ...touch(2, 250, 200), isPrimary: false })
		cam.onPointerMove(touch(2, 300, 200))
		expect(cam.zoom.value).toBe(2.25)
	})

	it("ignores a mouse press on a chip", () => {
		const cam = camera()
		cam.onChipPointerDown({ pointerId: 1, pointerType: "mouse", button: 0, clientX: 0, clientY: 0, currentTarget: box })
		expect(cam.isPressed()).toBe(false)
	})
})
