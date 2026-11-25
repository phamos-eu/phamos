import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { effectScope, reactive } from "vue"

// Production logged "Cannot access 'T' before initialization" when a cockpit opened in Ophice:
// MiniMap's `tile` read `wide` before `const wide` ran, through useMapCamera's watch getters.
// This runs the component's <script setup> on its own, with the browser bits it touches stubbed.

vi.mock("frappe-ui", () => ({ FeatherIcon: {} }))

function stubBrowser() {
	const store = {}
	vi.stubGlobal("window", {
		innerWidth: 1280,
		innerHeight: 800,
		matchMedia: () => ({ matches: false }),
		addEventListener() {},
		removeEventListener() {},
	})
	vi.stubGlobal("localStorage", {
		getItem: (key) => store[key] ?? null,
		setItem: (key, value) => (store[key] = String(value)),
	})
	vi.stubGlobal(
		"ResizeObserver",
		class {
			observe() {}
			disconnect() {}
		}
	)
}

async function runSetup(props, emitted = []) {
	const { default: MiniMap } = await import("./MiniMap.vue")
	const scope = effectScope()
	const emit = (name, ...args) => emitted.push([name, ...args])
	const state = scope.run(() => MiniMap.setup(reactive(props), { emit, expose() {}, attrs: {}, slots: {} }))
	return { state, scope }
}

describe("MiniMap setup (Ophice over a cockpit, #2109)", () => {
	beforeEach(() => {
		vi.resetModules()
		vi.spyOn(console, "warn").mockImplementation(() => {})
		stubBrowser()
	})
	afterEach(() => {
		vi.unstubAllGlobals()
		vi.restoreAllMocks()
	})

	it("sets up without reading a value before it is declared", async () => {
		const me = { name: "me", x: 3, y: 4 }
		const { state, scope } = await runSetup({ cols: 40, rows: 25, me, meeting: false })
		expect(state.tile.value).toBeGreaterThan(0)
		scope.stop()
	})

	// Also guards storedSize(): if SIZE_KEY ever moved below it, its catch would hide the error and
	// fall back to the default (tall) size, so `wide` would be false here.
	it("sets up in a meeting with a wide panel, where the panel's height also limits the tile", async () => {
		localStorage.setItem("phamos_ophice_mini_map_size", JSON.stringify({ w: 900, h: 300 }))
		const me = { name: "me", x: 3, y: 4 }
		const { state, scope } = await runSetup({ cols: 40, rows: 25, me, meeting: true })
		expect(state.wide.value).toBe(true)
		expect(state.tile.value).toBeGreaterThan(0)
		scope.stop()
	})
})

// Docked in the cockpit's sidebar (#2155) instead of a pop-out window.
describe("MiniMap docked in the cockpit sidebar (#2155)", () => {
	const me = { name: "me", x: 3, y: 4 }
	const dock = { left: 8, top: 560, width: 192, height: 200, bottom: 760, max: 480 }
	const press = (x, y) => ({ button: 0, clientX: x, clientY: y, preventDefault() {} })

	beforeEach(() => {
		vi.resetModules()
		vi.spyOn(console, "warn").mockImplementation(() => {})
		stubBrowser()
	})
	afterEach(() => {
		vi.unstubAllGlobals()
		vi.restoreAllMocks()
	})

	it("docks by default: at the spot's place and width, held at its bottom", async () => {
		const { state, scope } = await runSetup({ cols: 40, rows: 25, me, dock })
		expect(state.isDocked.value).toBe(true)
		expect(state.panelStyle.value).toMatchObject({ left: "8px", width: "192px", bottom: "40px", maxHeight: "480px" })
		scope.stop()
	})

	it("hovers when the cockpit has no sidebar to dock in", async () => {
		const { state, scope } = await runSetup({ cols: 40, rows: 25, me, dock: null })
		expect(state.isDocked.value).toBe(false)
		expect(state.panelStyle.value.bottom).toBeUndefined()
		scope.stop()
	})

	it("stays tall in a meeting while docked, even with a wide hovering size", async () => {
		localStorage.setItem("phamos_ophice_mini_map_size", JSON.stringify({ w: 900, h: 300 }))
		const { state, scope } = await runSetup({ cols: 40, rows: 25, me, meeting: true, dock })
		expect(state.wide.value).toBe(false)
		expect(state.panelStyle.value).toMatchObject({ height: "480px" })
		scope.stop()
	})

	it("comes out only once the pointer moves, hovers where it is let go, and docks again on the spot", async () => {
		const { state, scope } = await runSetup({ cols: 40, rows: 25, me, dock })
		// A click on the header (no move) leaves it docked.
		state.startDrag(press(60, 580))
		state.onDrag(press(62, 581))
		state.endDrag(press(62, 581))
		expect(state.isDocked.value).toBe(true)

		// Dragged out over the cockpit page: it hovers there, and that is remembered.
		state.startDrag(press(60, 580))
		state.onDrag(press(500, 300))
		expect(state.isDocked.value).toBe(false)
		state.endDrag(press(500, 300))
		expect(state.isDocked.value).toBe(false)
		expect(localStorage.getItem("phamos_ophice_mini_map_docked")).toBe("0")

		// Dragged back onto the sidebar's spot: docked.
		state.startDrag(press(500, 300))
		state.onDrag(press(90, 740))
		state.endDrag(press(90, 740))
		expect(state.isDocked.value).toBe(true)
		expect(localStorage.getItem("phamos_ophice_mini_map_docked")).toBe("1")
		scope.stop()
	})

	it("asks for a drop target while it is dragged, and for nothing while it hovers", async () => {
		localStorage.setItem("phamos_ophice_mini_map_docked", "0")
		const emitted = []
		const { state, scope } = await runSetup({ cols: 40, rows: 25, me, dock }, emitted)
		const sizes = () => emitted.filter(([name]) => name === "dock-size").map(([, size]) => size)
		expect(sizes().at(-1)).toEqual({ height: 0, target: false })
		state.startDrag(press(500, 300))
		state.onDrag(press(400, 300))
		await Promise.resolve()
		expect(sizes().at(-1)).toMatchObject({ target: true })
		expect(sizes().at(-1).height).toBeGreaterThan(0)
		state.endDrag(press(400, 300))
		await Promise.resolve()
		expect(sizes().at(-1)).toEqual({ height: 0, target: false })
		scope.stop()
	})

	it("docks with the header button", async () => {
		localStorage.setItem("phamos_ophice_mini_map_docked", "0")
		const { state, scope } = await runSetup({ cols: 40, rows: 25, me, dock })
		expect(state.isDocked.value).toBe(false)
		state.setDocked(true)
		expect(state.isDocked.value).toBe(true)
		scope.stop()
	})
})
