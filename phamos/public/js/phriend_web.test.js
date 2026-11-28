import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

// The website loader (#2104) runs as soon as it is imported: each test stubs the page and imports
// it fresh. Covers the two guards from the AI review of !1310.

function stubPage({ ballOnPage = false, assets = { "phriend_web_app.bundle.js": "/assets/phamos/dist/js/app.js" } } = {}) {
	const frappe = { boot: { assets_json: assets } }
	vi.stubGlobal("frappe", frappe)
	vi.stubGlobal("window", { frappe })
	vi.stubGlobal("document", {
		cookie: "system_user=yes; sid=x",
		readyState: "complete",
		getElementById: (id) => (ballOnPage && id === "phriend-root" ? {} : null),
		head: { appendChild() {} },
		createElement: () => ({ remove() {} }),
		addEventListener() {},
	})
	const fetch = vi.fn(async () => ({ ok: true, json: async () => ({ message: null }) }))
	vi.stubGlobal("fetch", fetch)
	return { fetch }
}

async function loadLoader() {
	await import("./phriend_web.bundle.js")
	// start() is async: let it run to its first await and beyond
	await new Promise((resolve) => setTimeout(resolve, 0))
}

describe("Phriend website loader (#2104)", () => {
	beforeEach(() => vi.resetModules())
	afterEach(() => {
		vi.unstubAllGlobals()
		vi.restoreAllMocks()
	})

	it("asks the server for a Desk user on a page without a ball", async () => {
		const { fetch } = stubPage()
		await loadLoader()
		expect(fetch).toHaveBeenCalledWith("/api/method/phamos.phriend.api.get_web_boot", expect.anything())
	})

	it("leaves a page that already has a Phriend ball alone", async () => {
		const { fetch } = stubPage({ ballOnPage: true })
		await loadLoader()
		expect(fetch).not.toHaveBeenCalled()
	})

	it("warns when the page carries no URL for the ball's bundle", async () => {
		const warn = vi.spyOn(console, "warn").mockImplementation(() => {})
		const { fetch } = stubPage({ assets: {} })
		await loadLoader()
		expect(fetch).not.toHaveBeenCalled()
		expect(warn).toHaveBeenCalledWith(expect.stringContaining("phriend_web_app.bundle.js missing"))
	})
})
