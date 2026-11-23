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

async function runSetup(props) {
	const { default: MiniMap } = await import("./MiniMap.vue")
	const scope = effectScope()
	const state = scope.run(() => MiniMap.setup(reactive(props), { emit() {}, expose() {}, attrs: {}, slots: {} }))
	return { state, scope }
}

describe("MiniMap setup (Ophice over a cockpit, #2074)", () => {
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

	it("sets up in a meeting with a wide panel, where the panel's height also limits the tile", async () => {
		localStorage.setItem("phamos_ophice_mini_map_size", JSON.stringify({ w: 900, h: 300 }))
		const me = { name: "me", x: 3, y: 4 }
		const { state, scope } = await runSetup({ cols: 40, rows: 25, me, meeting: true })
		expect(state.wide.value).toBe(true)
		expect(state.tile.value).toBeGreaterThan(0)
		scope.stop()
	})
})
