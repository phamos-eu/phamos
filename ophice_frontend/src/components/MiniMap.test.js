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

// Docked in the cockpit's right sidebar (#2155) instead of a pop-out window.
describe("MiniMap docked in the cockpit's right sidebar (#2155)", () => {
	const me = { name: "me", x: 3, y: 4 }
	const dock = { rect: { left: 992, top: 0, width: 288, height: 800, bottom: 800 } }
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

	it("docks by default and fills the right sidebar", async () => {
		const { state, scope } = await runSetup({ cols: 40, rows: 25, me, dock })
		expect(state.isDocked.value).toBe(true)
		expect(state.panelStyle.value).toEqual({ left: "992px", top: "0px", width: "288px", height: "800px" })
		scope.stop()
	})

	it("stays out of sight while the sidebar opens", async () => {
		const { state, scope } = await runSetup({ cols: 40, rows: 25, me, dock: { rect: null } })
		expect(state.isDocked.value).toBe(true)
		expect(state.panelStyle.value.visibility).toBe("hidden")
		scope.stop()
	})

	it("hovers when the cockpit has no dock", async () => {
		const { state, scope } = await runSetup({ cols: 40, rows: 25, me, dock: null })
		expect(state.isDocked.value).toBe(false)
		expect(state.panelStyle.value.visibility).toBeUndefined()
		scope.stop()
	})

	it("stays tall in a meeting while docked, even with a wide hovering size", async () => {
		localStorage.setItem("phamos_ophice_mini_map_size", JSON.stringify({ w: 900, h: 300 }))
		const { state, scope } = await runSetup({ cols: 40, rows: 25, me, meeting: true, dock })
		expect(state.wide.value).toBe(false)
		scope.stop()
	})

	it("comes out only once the pointer moves, hovers where it is let go, and docks again on the right", async () => {
		const { state, scope } = await runSetup({ cols: 40, rows: 25, me, dock })
		// A click on the header (no move) leaves it docked.
		state.startDrag(press(1050, 12))
		state.onDrag(press(1052, 13))
		state.endDrag(press(1052, 13))
		expect(state.isDocked.value).toBe(true)

		// Dragged out over the cockpit page: it hovers there, and that is remembered.
		state.startDrag(press(1050, 12))
		state.onDrag(press(500, 300))
		expect(state.isDocked.value).toBe(false)
		state.endDrag(press(500, 300))
		expect(state.isDocked.value).toBe(false)
		expect(localStorage.getItem("phamos_ophice_mini_map_docked")).toBe("0")

		// Dragged back onto the drop strip: docked.
		state.startDrag(press(500, 300))
		state.onDrag(press(1100, 400))
		state.endDrag(press(1100, 400))
		expect(state.isDocked.value).toBe(true)
		expect(localStorage.getItem("phamos_ophice_mini_map_docked")).toBe("1")
		scope.stop()
	})

	it("opens the sidebar while docked, asks for the drop strip while dragged, and closes it while hovering", async () => {
		const emitted = []
		const { state, scope } = await runSetup({ cols: 40, rows: 25, me, dock }, emitted)
		const wants = () => emitted.filter(([name]) => name === "dock-want").map(([, want]) => want)
		expect(wants().at(-1)).toEqual({ docked: true, target: false })
		state.startDrag(press(1050, 12))
		state.onDrag(press(400, 300))
		await Promise.resolve()
		expect(wants().at(-1)).toEqual({ docked: false, target: true })
		state.endDrag(press(400, 300))
		await Promise.resolve()
		expect(wants().at(-1)).toEqual({ docked: false, target: false })
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
