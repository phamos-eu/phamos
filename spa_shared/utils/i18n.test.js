import { afterEach, describe, expect, it } from "vitest"
import { __ } from "./i18n.js"

describe("__", () => {
	afterEach(() => delete globalThis.window)

	it("returns the text when there is no translation", () => {
		expect(__("Create")).toBe("Create")
		expect(__("{0} min", [5])).toBe("5 min")
	})

	it("translates and fills placeholders", () => {
		globalThis.window = { frappe: { boot: { __messages: { Create: "Erstellen", "{0} of {1}": "{0} von {1}" } } } }
		expect(__("Create")).toBe("Erstellen")
		expect(__("{0} of {1}", [2, 5])).toBe("2 von 5")
		expect(__("{0} of {1}", [2])).toBe("2 von {1}")
	})
})
