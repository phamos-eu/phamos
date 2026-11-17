// Run with `yarn test:spa` (vitest globals, see personal_frontend/vitest.config.js).
import {
	addAttendees,
	addDepartment,
	departmentState,
	isPicked,
	moveAttendee,
	normalizeAttendees,
	peopleIndex,
	personFor,
	removeAttendee,
} from "./attendeePicker.js"

const SALES = {
	department: "Sales",
	people: [
		{ email: "ann@phamos.eu", name: "Ann" },
		{ email: "ben@phamos.eu", name: "Ben" },
	],
}
const EMPTY = { required: [], optional: [] }

describe("attendee picker", () => {
	it("adds new people to required, once", () => {
		let a = addAttendees(EMPTY, ["ann@phamos.eu"])
		a = addAttendees(a, ["ANN@phamos.eu", "ben@phamos.eu"])
		expect(a).toEqual({ required: ["ann@phamos.eu", "ben@phamos.eu"], optional: [] })
	})

	it("adds a whole department, skipping people already picked in either section", () => {
		const a = addDepartment({ required: [], optional: ["ben@phamos.eu"] }, SALES)
		expect(a).toEqual({ required: ["ann@phamos.eu"], optional: ["ben@phamos.eu"] })
	})

	it("moves people between the sections and back", () => {
		let a = addDepartment(EMPTY, SALES)
		a = moveAttendee(a, "ann@phamos.eu", "optional")
		expect(a).toEqual({ required: ["ben@phamos.eu"], optional: ["ann@phamos.eu"] })
		a = moveAttendee(a, "ann@phamos.eu", "required")
		expect(a).toEqual({ required: ["ben@phamos.eu", "ann@phamos.eu"], optional: [] })
	})

	it("ignores moves of unknown people or to unknown sections", () => {
		const a = addDepartment(EMPTY, SALES)
		expect(moveAttendee(a, "zoe@phamos.eu", "optional")).toBe(a)
		expect(moveAttendee(a, "ann@phamos.eu", "somewhere")).toBe(a)
	})

	it("removes from whichever section holds the address", () => {
		const a = removeAttendee({ required: ["ann@phamos.eu"], optional: ["Ben@phamos.eu"] }, "ben@phamos.eu")
		expect(a).toEqual({ required: ["ann@phamos.eu"], optional: [] })
	})

	it("tells whether a department is all, partly or not picked", () => {
		expect(departmentState(EMPTY, SALES)).toBe("none")
		expect(departmentState(addAttendees(EMPTY, ["ann@phamos.eu"]), SALES)).toBe("some")
		expect(departmentState(addDepartment(EMPTY, SALES), SALES)).toBe("all")
	})

	it("keeps an address in both sections only as required", () => {
		expect(normalizeAttendees({ required: ["x@ex.com"], optional: ["X@ex.com", "y@ex.com"] })).toEqual({
			required: ["x@ex.com"],
			optional: ["y@ex.com"],
		})
	})

	it("keeps addresses of people outside the list (external guests) with their address as name", () => {
		const index = peopleIndex([SALES])
		expect(personFor(index, "ann@phamos.eu").name).toBe("Ann")
		expect(personFor(index, "guest@partner.de")).toEqual({ email: "guest@partner.de", name: "guest@partner.de", image: null })
		expect(isPicked({ required: ["guest@partner.de"], optional: [] }, "Guest@partner.de")).toBe(true)
	})
})
