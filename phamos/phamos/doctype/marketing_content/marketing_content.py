import re
import json
import frappe
from frappe.website.website_generator import WebsiteGenerator
from frappe.utils import get_datetime

# Full-string match: same character set as Frappe's EMAIL_MATCH_PATTERN but anchored with ^ and $
# so trailing garbage like a slash is rejected rather than silently ignored.
_STRICT_EMAIL_RE = re.compile(
    r"^[a-z0-9][a-z0-9!#$%&'*+/=?^_`{|}~-]*(?:\.[a-z0-9!#$%&'*+/=?^_`{|}~-]+)*"
    r"@(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$",
    re.IGNORECASE,
)


def _clean_and_validate_email(raw_email):
    """Return the trimmed, validated bare email address or throw."""
    raw = (raw_email or "").strip()
    # Frappe parses display-name formats ("Name <addr>") and returns the bare address.
    # Returns empty string when invalid.
    parsed = frappe.utils.validate_email_address(raw)
    if not parsed:
        frappe.throw(frappe._("Please enter a valid email address"))
    cleaned = parsed.split(",")[0].strip()
    if not _STRICT_EMAIL_RE.match(cleaned):
        frappe.throw(frappe._("Please enter a valid email address"))
    return cleaned


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
    raw_email = (email or "").strip()
    try:
        email = _clean_and_validate_email(email)
    except Exception:
        return {"status": "invalid_email"}
    email_group = frappe.db.get_value("Marketing Content", event_name, "email_group")
    if not email_group:
        frappe.throw(frappe._("This event does not have an Email Group configured"))
    if frappe.db.exists("Email Group Member", {"email_group": email_group, "email": email}):
        return {"status": "already_subscribed", "email": email,
                "raw_email": raw_email if raw_email != email else None}
    frappe.get_doc({
        "doctype": "Email Group Member",
        "email_group": email_group,
        "email": email,
    }).insert(ignore_permissions=True)
    frappe.db.commit()
    return {"status": "ok", "email": email,
            "raw_email": raw_email if raw_email != email else None}


@frappe.whitelist()
def create_newsletter_for_event(event_name):
    doc = frappe.get_doc("Marketing Content", event_name)
    if not doc.email_group:
        frappe.throw(frappe._("Please set an Email Group on this Marketing Content before creating a Newsletter."))
    user_info = frappe.db.get_value(
        "User", frappe.session.user, ["full_name", "email"], as_dict=True
    )
    now = frappe.utils.now_datetime()
    title_slug = frappe.scrub(doc.title).replace("_", "-")
    base_name = f"{now.strftime('%Y-%m')}-{title_slug}"
    newsletter_name = base_name
    subject = doc.title
    counter = 2
    while frappe.db.exists("Newsletter", newsletter_name):
        newsletter_name = f"{base_name}-{counter}"
        subject = f"{doc.title}"
        counter += 1
    newsletter = frappe.new_doc("Newsletter")
    newsletter.subject = subject
    newsletter.sender_name = user_info.full_name or frappe.session.user
    newsletter.sender_email = user_info.email
    newsletter.custom_marketing_content = doc.name
    newsletter.append("email_group", {"email_group": doc.email_group})
    newsletter.insert(set_name=newsletter_name)
    return newsletter.name
