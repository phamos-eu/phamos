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
