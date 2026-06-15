import frappe
from frappe.utils import flt
from frappe.query_builder import DocType


def execute():

    DNI = DocType("Delivery Note Item")
    SOI = DocType("Sales Order Item")
    DN  = DocType("Delivery Note")

    # ── Step 1: MIS rows clean
    mis_rows = (
        frappe.qb.from_(DNI)
        .select(DNI.name)
        .where(DNI.parenttype == "Monthly Implementation Summary")
        .where(
            (DNI.against_sales_order.isnotnull())
            | (DNI.so_detail.isnotnull())
        )
    ).run(as_dict=True)

    if mis_rows:
        (
            frappe.qb.update(DNI)
            .set(DNI.against_sales_order, None)
            .set(DNI.so_detail, None)
            .where(DNI.parenttype == "Monthly Implementation Summary")
            .where(
                (DNI.against_sales_order.isnotnull())
                | (DNI.so_detail.isnotnull())
            )
        ).run()
        frappe.db.commit()
        print(f"Cleaned {len(mis_rows)} MIS rows with SO reference.")
    # ── Step 2: SO Items delivered_qty recalculate
    so_items = (
        frappe.qb.from_(SOI)
        .select(
            SOI.name,
            SOI.parent.as_("sales_order"),
            SOI.item_code,
            SOI.delivered_qty,
        )
        .where(SOI.docstatus == 1)
    ).run(as_dict=True)

    if not so_items:
        return

    print(f"Total SO Items check hongi: {len(so_items)}")

    affected_so = set()

    for soi in so_items:
        result = (
            frappe.qb.from_(DNI)
            .inner_join(DN).on(DN.name == DNI.parent)
            .select(DNI.qty)
            .where(DNI.so_detail  == soi.name)
            .where(DNI.parenttype == "Delivery Note")
            .where(DN.docstatus   == 1)
        ).run(as_dict=True)

        actual_qty = flt(sum(flt(r.qty) for r in result))

        if flt(soi.delivered_qty) != actual_qty:
            print(
                f"  Fix: SO {soi.sales_order} | {soi.item_code}: "
                f"{soi.delivered_qty} → {actual_qty}"
            )
            frappe.db.set_value(
                "Sales Order Item",
                soi.name,
                "delivered_qty",
                actual_qty,
            )
            affected_so.add(soi.sales_order)

    frappe.db.commit()

 # ── Step 3: Recalculate affected Sales Orders
    for so_name in affected_so:
        try:
            so = frappe.get_doc("Sales Order", so_name)

            # Recalculate all derived values including per_delivered
            so.save(ignore_permissions=True)

            # Update status after recalculation
            so.set_status(update=True)
            so.notify_update()

            print(
                f"Updated SO {so.name}: "
                f"per_delivered={so.per_delivered}, "
                f"status={so.status}"
            )

        except Exception:
            frappe.log_error(
                title=f"Patch: SO {so_name} update failed",
                message=frappe.get_traceback(),
            )

    frappe.db.commit()
