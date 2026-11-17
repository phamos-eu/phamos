import { describe, expect, it, vi } from "vitest"
import { page_background, watch_theme } from "./util.js"

describe("page_background", () => {
	it("takes the first background that is set", () => {
		expect(page_background(["rgb(23, 23, 23)", "rgb(255, 255, 255)"], "dark")).toBe("rgb(23, 23, 23)")
		expect(page_background(["rgba(0, 0, 0, 0)", "rgb(30, 30, 30)"], "light")).toBe("rgb(30, 30, 30)")
	})
	it("skips transparent backgrounds in every notation", () => {
		for (const c of ["", "transparent", "rgba(0, 0, 0, 0)", "rgb(0 0 0 / 0)", "rgba(10, 10, 10, 0.0)"])
			expect(page_background([c], "light")).toBe("#ffffff")
	})
	it("keeps a solid black background", () => {
		expect(page_background(["rgb(0, 0, 0)"], "light")).toBe("rgb(0, 0, 0)")
		expect(page_background(["rgb(0 0 0)"], "light")).toBe("rgb(0 0 0)")
	})
	it("keeps half-transparent backgrounds", () => {
		expect(page_background(["rgba(0, 0, 0, 0.5)"], "light")).toBe("rgba(0, 0, 0, 0.5)")
	})
	it("falls back to dark grey in dark mode, not white", () => {
		expect(page_background(["rgba(0, 0, 0, 0)", "rgba(0, 0, 0, 0)"], "dark")).toBe("#171717")
	})
})

describe("watch_theme", () => {
	it("re-applies when the OS switches between light and dark", () => {
		const observe = vi.fn()
		vi.stubGlobal("MutationObserver", class { constructor(cb) { this.cb = cb } observe(...a) { observe(...a) } })
		const listeners = {}
		const os_dark = { addEventListener: (type, fn) => (listeners[type] = fn) }
		const apply = vi.fn()
		const root = {}

		watch_theme(apply, root, os_dark)
		expect(observe).toHaveBeenCalledWith(root, { attributes: true, attributeFilter: ["data-theme"] })
		listeners.change()
		expect(apply).toHaveBeenCalledTimes(1)
		vi.unstubAllGlobals()
	})
	it("works without matchMedia", () => {
		vi.stubGlobal("MutationObserver", class { observe() {} })
		expect(() => watch_theme(() => {}, {}, null)).not.toThrow()
		vi.unstubAllGlobals()
	})
})
