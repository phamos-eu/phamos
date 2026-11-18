import { describe, expect, it, vi } from "vitest"
import { FILTERABLE_FIELDS, filterFields, restrictFilterFields } from "./filterFields.js"

// A stand-in for Frappe v15: FilterGroup._push_new_filter creates every row with
// `new frappe.ui.Filter(args)`, and Filter copies its options onto itself ($.extend).
function frappeLike() {
	const ui = {
		Filter: class {
			constructor(opts) {
				Object.assign(this, opts)
			}
		},
	}
	const group = {
		filters: [],
		_push_new_filter(doctype, fieldname) {
			const filter = new ui.Filter({ doctype, fieldname })
			this.filters.push(filter)
			return filter
		},
	}
	return { ui, group }
}

describe("filterFields", () => {
	it("offers only the panel's fields, ID first", () => {
		const fields = filterFields("Project", (doctype, fieldname) => ({ fieldname, parent: doctype }))
		expect(fields.map((f) => f.fieldname)).toEqual(FILTERABLE_FIELDS.Project)
		expect(fields[0]).toMatchObject({ fieldname: "name", label: "ID", parent: "Project" })
	})

	it("skips fields the doctype does not have", () => {
		const fields = filterFields("Project", (doctype, fieldname) => (fieldname === "status" ? { fieldname } : null))
		expect(fields.map((f) => f.fieldname)).toEqual(["name", "status"])
	})
})

describe("restrictFilterFields", () => {
	it("gives every row (first, + Add a Filter, re-added) the field list", () => {
		const { ui, group } = frappeLike()
		const fields = [{ fieldname: "name" }]
		expect(restrictFilterFields(group, fields, ui)).toBe(true)
		group._push_new_filter("Project", "name")
		group._push_new_filter("Project", "status")
		group._push_new_filter("Project", "customer")
		expect(group.filters.map((f) => f.filter_fields)).toEqual([fields, fields, fields])
	})

	it("restores frappe.ui.Filter after each row, also when creating it fails", () => {
		const { ui, group } = frappeLike()
		const Filter = ui.Filter
		restrictFilterFields(group, [], ui)
		group._push_new_filter("Project", "name")
		expect(ui.Filter).toBe(Filter)
		const failing = { _push_new_filter: () => { throw new Error("boom") } }
		restrictFilterFields(failing, [], ui)
		expect(() => failing._push_new_filter()).toThrow("boom")
		expect(ui.Filter).toBe(Filter)
	})

	it("warns and changes nothing when Frappe's FilterGroup internals are gone", () => {
		const { ui } = frappeLike()
		const warn = vi.fn()
		const group = {}
		expect(restrictFilterFields(group, [], ui, warn)).toBe(false)
		expect(warn).toHaveBeenCalledOnce()
		expect(group._push_new_filter).toBeUndefined()
	})
})
