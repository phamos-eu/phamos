import frappe
from frappe import _
from frappe.query_builder import Order
from frappe.query_builder.functions import Coalesce

LEAD_STATUSES = [
    "Lead", "Open", "Replied", "Opportunity", "Quotation",
    "Lost Quotation", "Interested", "Converted", "Do Not Contact",
]


@frappe.whitelist()
def get_leads():
    """Return all non-disabled leads; is_mine when user is lead_owner or has an open ToDo."""
    user = frappe.session.user

    Lead = frappe.qb.DocType("Lead")
    User = frappe.qb.DocType("User")
    ToDo = frappe.qb.DocType("ToDo")

    leads = (
        frappe.qb.from_(Lead)
        .left_join(User).on(User.name == Lead.lead_owner)
        .select(
            Lead.name,
            Lead.lead_name,
            Lead.company_name,
            Lead.status,
            Lead.lead_owner,
            Lead.source,
            Lead.email_id,
            Lead.mobile_no,
            Lead.territory,
            Lead.creation,
            Lead.modified,
            Coalesce(User.full_name, Lead.lead_owner).as_("owner_full_name"),
        )
        .where(Lead.disabled == 0)
        .orderby(Lead.modified, order=Order.desc)
    ).run(as_dict=True)

    # Collect leads assigned to the user via open ToDo
    assigned = (
        frappe.qb.from_(ToDo)
        .select(ToDo.reference_name)
        .where(
            (ToDo.reference_type == "Lead")
            & (ToDo.status == "Open")
            & (ToDo.allocated_to == user)
        )
    ).run(as_dict=True)
    assigned_set = {r.reference_name for r in assigned}

    for lead in leads:
        lead["is_mine"] = lead.get("lead_owner") == user or lead["name"] in assigned_set

    return leads


@frappe.whitelist()
def set_lead_status(lead_name, status):
    """Update lead status directly from the panel."""
    if status not in LEAD_STATUSES:
        frappe.throw(_("Invalid lead status: {0}").format(status))
    doc = frappe.get_doc("Lead", lead_name)
    doc.status = status
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {"name": lead_name, "status": status}
