import frappe
from frappe.website.website_generator import WebsiteGenerator
from frappe.utils import get_datetime


class DanceEvent(WebsiteGenerator):
    website = frappe._dict(
        page_title_field="title",
        condition_field="published",
        template="phamos/phamos/doctype/dance_event/templates/dance_event.html",
        row_template="phamos/phamos/doctype/dance_event/templates/dance_event_row.html",
    )

    def before_save(self):
        if not self.route:
            self.route = "dance-events/" + self.title.lower().replace(" ", "-")

    def get_context(self, context):
        context.title = self.title
        context.subtitle = self.subtitle
        context.event_type = self.event_type
        context.status = self.status
        context.starts_on = self.starts_on
        context.ends_on = self.ends_on
        context.location = self.location
        context.city = self.city
        context.image = self.image
        context.intro = self.intro
        context.description = self.description
        context.organizer_name = self.organizer_name
        context.organizer_email = self.organizer_email
        context.going_count = self.going_count or 0
        context.maybe_count = self.maybe_count or 0
        context.not_going_count = self.not_going_count or 0
        context.parents = [{"title": "Dance Events", "route": "dance-events"}]

        # Pre-formatted date/time parts for the calendar display
        if self.starts_on:
            dt = get_datetime(self.starts_on)
            context.starts_day_num  = dt.strftime("%d")        # "25"
            context.starts_day_name = dt.strftime("%a").upper() # "THU"
            context.starts_month    = dt.strftime("%b").upper() # "MAR"
            context.starts_year     = dt.strftime("%Y")         # "2026"
            context.starts_time     = dt.strftime("%H:%M")      # "20:00"
        if self.ends_on:
            dt_end = get_datetime(self.ends_on)
            context.ends_time = dt_end.strftime("%H:%M")
        context.metatags = {
            "title": self.title,
            "description": self.intro or "",
            "image": self.image or "",
        }


@frappe.whitelist(allow_guest=True)
def submit_interest(event_name, response, previous_response=None):
    """Record or change a visitor's interest response (Going / Maybe / Not Going)."""
    allowed = {"Going", "Maybe", "Not Going"}
    if response not in allowed:
        frappe.throw(frappe._("Invalid response"))
    if previous_response not in allowed:
        previous_response = None

    field_map = {
        "Going":     "going_count",
        "Maybe":     "maybe_count",
        "Not Going": "not_going_count",
    }

    # Decrement the previous choice (floor at 0) when changing
    if previous_response and previous_response != response:
        prev_field = field_map[previous_response]
        frappe.db.sql(
            "UPDATE `tabDance Event`"
            f" SET `{prev_field}` = GREATEST(0, COALESCE(`{prev_field}`, 0) - 1)"
            " WHERE name = %s",
            event_name,
        )

    # Increment the new choice
    new_field = field_map[response]
    frappe.db.sql(
        "UPDATE `tabDance Event`"
        f" SET `{new_field}` = COALESCE(`{new_field}`, 0) + 1"
        " WHERE name = %s",
        event_name,
    )
    frappe.db.commit()

    counts = frappe.db.get_value(
        "Dance Event", event_name,
        ["going_count", "maybe_count", "not_going_count"],
        as_dict=True,
    )
    return {"status": "ok", "counts": counts}
