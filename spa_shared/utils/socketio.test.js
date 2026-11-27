import { describe, expect, it } from "vitest"
import { socketioOptions } from "./socketio.js"

describe("socketio options", () => {
	it("gives frappe-ui the bench's socket.io port from the boot", () => {
		expect(socketioOptions({ socketio_port: 9003 })).toEqual({ port: 9003 })
	})
	it("leaves the port to frappe-ui when the boot has none", () => {
		expect(socketioOptions({})).toEqual({ port: undefined })
		expect(socketioOptions(undefined)).toEqual({ port: undefined })
	})
})
