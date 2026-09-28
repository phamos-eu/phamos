import frappe

PROJECT = "Cost Center - HR Department"
IMPLEMENTATION = "00189 suncycle"

def execute():
    ts = frappe.qb.DocType("Timesheet")
    names = (
        frappe.qb.from_(ts)
        .select(ts.name)
        .where(ts.parent_project == PROJECT)
        .where(ts.custom_implementation == IMPLEMENTATION)
    ).run(pluck="name")

    if names:
        (
            frappe.qb.update(ts)
            .set(ts.custom_implementation, None)
            .where(ts.name.isin(names))
        ).run()

    td = frappe.qb.DocType("Timesheet Detail")
    names = (
        frappe.qb.from_(td)
        .select(td.name)
        .where(td.project == PROJECT)
        .where(td.custom_implementation == IMPLEMENTATION)
    ).run(pluck="name")

    if names:
        (
            frappe.qb.update(td)
            .set(td.custom_implementation, None)
            .where(td.name.isin(names))
        ).run()