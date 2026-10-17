import { describe, expect, it } from "vitest"
import { scrollOverflow } from "./scrollOverflow.js"

describe("scroll overflow", () => {
	it("sees content below a box that is not scrolled yet", () => {
		expect(scrollOverflow({ scrollTop: 0, clientHeight: 600, scrollHeight: 9000 })).toEqual({ above: false, below: true })
	})
	it("sees both sides in the middle", () => {
		expect(scrollOverflow({ scrollTop: 500, clientHeight: 600, scrollHeight: 9000 })).toEqual({ above: true, below: true })
	})
	it("sees nothing more at the end or when everything fits", () => {
		expect(scrollOverflow({ scrollTop: 8399, clientHeight: 600, scrollHeight: 9000 })).toEqual({ above: true, below: false })
		expect(scrollOverflow({ scrollTop: 0, clientHeight: 600, scrollHeight: 400 })).toEqual({ above: false, below: false })
	})
})
