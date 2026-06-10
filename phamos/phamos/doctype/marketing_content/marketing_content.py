import frappe
from frappe.website.website_generator import WebsiteGenerator
from frappe.utils import get_datetime


class MarketingContent(WebsiteGenerator):
    website = frappe._dict(
        page_title_field="title",
        condition_field="published",
        template="phamos/phamos/doctype/marketing_content/templates/marketing_content.html",
        row_template="phamos/phamos/doctype/marketing_content/templates/marketing_content_row.html",
    )

    def before_save(self):
        if not self.route:
            self.route = "events/" + self.title.lower().replace(" ", "-")
        if not self.starts_on and not self.date_note:
            frappe.throw(
                frappe._("Please set either a confirmed Start Date or a Date Note "
                         "(e.g. 'Expected: July 2026') before saving.")
            )
        if self.starts_on and self.date_note:
            frappe.throw(
                frappe._("Set either a confirmed Start Date or a Date Note — not both.")
            )

    def get_context(self, context):
        context.title = self.title
        context.subtitle = self.subtitle
        context.event_type = self.event_type
        context.status = self.status
        context.date_note = self.date_note
        context.starts_on = self.starts_on
        context.ends_on = self.ends_on
        context.location = self.location
        context.city = self.city
        context.map_link = self.map_link
        context.image = self.image
        context.intro = self.intro
        context.description = self.description
        context.organizer_name = self.organizer_name
        context.organizer_email = self.organizer_email
        context.going_count = self.going_count or 0
        context.maybe_count = self.maybe_count or 0
        context.not_going_count = self.not_going_count or 0
        context.registration_open = self.registration_open
        context.max_attendees = self.max_attendees or 0
        context.spots_left = None
        if self.registration_open:
            registered_count = frappe.db.count(
                "Marketing Event Registration",
                filters={"event": self.name, "status": ["!=", "Cancelled"]},
            )
            if self.max_attendees:
                context.spots_left = max(0, self.max_attendees - registered_count)
        context.parents = [{"title": "Events", "route": "events"}]
        if self.starts_on:
            dt = get_datetime(self.starts_on)
            context.starts_day_num  = dt.strftime("%d")
            context.starts_day_name = dt.strftime("%a").upper()
            context.starts_month    = dt.strftime("%b").upper()
            context.starts_year     = dt.strftime("%Y")
            context.starts_time     = dt.strftime("%H:%M")
        if self.ends_on:
            dt_end = get_datetime(self.ends_on)
            context.ends_time = dt_end.strftime("%H:%M")
        context.metatags = {
            "title": self.title,
            "description": self.intro or "",
            "image": self.image or "",
        }

@frappe.whitelist()
def get_linked_checklists(doctype, name):
    return frappe.get_all(
        "Checklist",
        filters={
            "document": doctype,
            "reference_record": name,
        },
        fields=[
            "name",
            "status",
            "completion_percentage",
        ],
        order_by="modified desc",
    )


@frappe.whitelist(allow_guest=True)
def get_interest_counts(event_name):
    counts = frappe.db.get_value(
        "Marketing Content", event_name,
        ["going_count", "maybe_count", "not_going_count"], as_dict=True,
    )
    return counts or {"going_count": 0, "maybe_count": 0, "not_going_count": 0}


@frappe.whitelist(allow_guest=True)
def submit_interest(event_name, response, previous_response=None):
    allowed = {"Yes", "Maybe", "No"}
    if response not in allowed:
        frappe.throw(frappe._("Invalid response"))
    if previous_response not in allowed:
        previous_response = None
    field_map = {"Yes": "going_count", "Maybe": "maybe_count", "No": "not_going_count"}
    if previous_response and previous_response != response:
        prev_field = field_map[previous_response]
        frappe.db.sql(
            "UPDATE `tabMarketing Content`"
            f" SET `{prev_field}` = GREATEST(0, COALESCE(`{prev_field}`, 0) - 1)"
            " WHERE name = %s", event_name,
        )
    new_field = field_map[response]
    frappe.db.sql(
        "UPDATE `tabMarketing Content`"
        f" SET `{new_field}` = COALESCE(`{new_field}`, 0) + 1"
        " WHERE name = %s", event_name,
    )
    frappe.db.commit()
    frappe.clear_document_cache("Marketing Content", event_name)
    counts = frappe.db.get_value(
        "Marketing Content", event_name,
        ["going_count", "maybe_count", "not_going_count"], as_dict=True,
    )
    return {"status": "ok", "counts": counts}


@frappe.whitelist(allow_guest=True)
def subscribe_to_event(event_name, email):
    if not frappe.db.exists("Marketing Content", event_name):
        frappe.throw(frappe._("Event not found"))
    if not frappe.utils.validate_email_address(email):
        frappe.throw(frappe._("Please enter a valid email address"))
    existing = frappe.db.exists(
        "Marketing Event Response", {"parent": event_name, "email": email}
    )
    if existing:
        return {"status": "already_subscribed"}
    child = frappe.get_doc({
        "doctype": "Marketing Event Response",
        "parenttype": "Marketing Content",
        "parent": event_name,
        "parentfield": "responses",
        "email": email,
        "subscribed_on": frappe.utils.now(),
    })
    child.insert(ignore_permissions=True)
    frappe.db.commit()
    return {"status": "ok"}
