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
        context.ticket_item = self.ticket_item
        context.email_group = self.email_group
        context.tc_name = self.tc_name
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


@frappe.whitelist(allow_guest=True)
def get_ticket_info(event_name):
    item_code = frappe.db.get_value("Marketing Content", event_name, "ticket_item")
    if not item_code:
        return None
    item = frappe.db.get_value("Item", item_code, ["item_name", "description", "standard_rate"], as_dict=True)
    if not item:
        return None
    item_price = frappe.db.get_value(
        "Item Price",
        {"item_code": item_code, "selling": 1},
        ["price_list_rate", "currency"],
        as_dict=True,
    )
    rate = item_price.price_list_rate if item_price else (item.standard_rate or 0)
    currency = item_price.currency if item_price else frappe.db.get_single_value("Global Defaults", "default_currency") or "EUR"

    item_tax_template = frappe.db.get_value("Marketing Content", event_name, "item_tax_template")
    tax_rate = 0.0
    tax_rows = []
    if item_tax_template:
        tax_detail_rows = frappe.get_all(
            "Item Tax Template Detail",
            filters={"parent": item_tax_template, "tax_rate": [">", 0]},
            fields=["tax_type", "tax_rate"],
            order_by="idx asc",
            limit=1,
        )
        for r in tax_detail_rows:
            row_rate = float(r.get("tax_rate") or 0)
            tax_rate += row_rate
            tax_rows.append({
                "account_head": r.get("tax_type") or "",
                "rate": row_rate,
            })

    event_title = frappe.db.get_value("Marketing Content", event_name, "title") or item.item_name

    tc_name = frappe.db.get_value("Marketing Content", event_name, "tc_name")
    tc_text = None
    if tc_name:
        tc_text = frappe.db.get_value("Terms and Conditions", tc_name, "terms")

    return {
        "item_code": item_code,
        "item_name": item.item_name,
        "event_title": event_title,
        "rate": float(rate),
        "currency": currency,
        "tax_rate": tax_rate,
        "tax_rows": tax_rows,
        "tc_text": tc_text,
    }


@frappe.whitelist(allow_guest=True)
def create_ticket_order(event_name, attendees, qty, invoice_data=None):
    if not frappe.db.exists("Marketing Content", event_name):
        frappe.throw(frappe._("Event not found"))

    item_code = frappe.db.get_value("Marketing Content", event_name, "ticket_item")
    if not item_code:
        frappe.throw(frappe._("No ticket item configured for this event"))

    qty = int(qty)
    if qty < 1:
        frappe.throw(frappe._("Quantity must be at least 1"))

    if isinstance(attendees, str):
        attendees = json.loads(attendees)
    if not attendees:
        frappe.throw(frappe._("At least one attendee is required"))

    if isinstance(invoice_data, str):
        invoice_data = json.loads(invoice_data) if invoice_data else None

    is_company_order = bool(invoice_data and invoice_data.get("company_name"))

    # --- Find or create customer from primary attendee ---
    primary = attendees[0]
    customer = _resolve_customer(primary["full_name"], primary["email"], is_company_order, invoice_data)

    # --- Item rate ---
    item_price = frappe.db.get_value(
        "Item Price",
        {"item_code": item_code, "selling": 1},
        ["price_list_rate", "price_list"],
        as_dict=True,
    )
    rate = item_price.price_list_rate if item_price else frappe.db.get_value("Item", item_code, "standard_rate") or 0
    price_list = item_price.price_list if item_price else "Standard Selling"
    company = frappe.db.get_single_value("Global Defaults", "default_company")

    # --- Default Sales Taxes and Charges Template ---
    tax_template_name = frappe.db.get_value(
        "Sales Taxes and Charges Template",
        {"company": company, "is_default": 1},
        "name",
    )

    # --- Draft Sales Order ---
    so = frappe.new_doc("Sales Order")
    so.customer = "Ticket Buyer Walk In"
    so.company = company
    so.po_no = f"Ticket purchase for {event_name}"
    so.po_date = frappe.utils.today()
    so.order_type = "Shopping Cart"
    so.transaction_date = frappe.utils.today()
    so.delivery_date = frappe.utils.today()
    so.selling_price_list = price_list
    so.ignore_pricing_rule = 1
    so.append("items", {
        "item_code": item_code,
        "qty": qty,
        "rate": rate,
        "delivery_date": frappe.utils.today(),
    })

    item_tax_template = frappe.db.get_value("Marketing Content", event_name, "item_tax_template")
    if item_tax_template:
        tax_detail_rows = frappe.get_all(
            "Item Tax Template Detail",
            filters={"parent": item_tax_template, "tax_rate": [">", 0]},
            fields=["tax_type", "tax_rate"],
            order_by="idx asc",
            limit=1,
        )
        default_cost_center = frappe.get_cached_value("Company", company, "cost_center")
        for tax_row in tax_detail_rows:
            so.append("taxes", {
                "charge_type": "On Net Total",
                "account_head": tax_row.tax_type,
                "rate": tax_row.tax_rate,
                "description": tax_row.tax_type,
                "cost_center": default_cost_center,
            })

    tc_name = frappe.db.get_value("Marketing Content", event_name, "tc_name")
    if tc_name:
        so.tc_name = tc_name

    so.flags.ignore_permissions = True
    so.insert()

    # --- Register each attendee ---
    for att in attendees:
        reg = frappe.new_doc("Marketing Event Registration")
        reg.event = event_name
        reg.full_name = att.get("full_name")
        reg.email = att.get("email")
        reg.registered_on = frappe.utils.now_datetime()
        reg.notes = "Sales Order: " + so.name
        reg.flags.ignore_permissions = True
        reg.insert()

    # --- Subscribe all attendees to the event email group ---
    email_group = frappe.db.get_value("Marketing Content", event_name, "email_group")
    if email_group:
        for att in attendees:
            att_email = att.get("email")
            if att_email and not frappe.db.exists("Email Group Member", {"email_group": email_group, "email": att_email}):
                frappe.get_doc({
                    "doctype": "Email Group Member",
                    "email_group": email_group,
                    "email": att_email,
                }).insert(ignore_permissions=True)

    frappe.db.commit()
    return {"sales_order": so.name, "customer": customer}


def _resolve_customer(full_name, email, is_company, invoice_data):
    # Look up existing customer linked to this email via Contact
    existing = frappe.db.get_value("Contact Email", {"email_id": email}, "parent")
    if existing:
        linked = frappe.db.get_value(
            "Dynamic Link",
            {"parenttype": "Contact", "parent": existing, "link_doctype": "Customer"},
            "link_name",
        )
        if linked and frappe.db.exists("Customer", linked):
            cust_display_name = frappe.db.get_value("Customer", linked, "customer_name")
            _maybe_create_address(linked, cust_display_name, invoice_data)
            return linked

    selling = frappe.get_single("Selling Settings")
    territory = selling.territory or "All Territories"

    if is_company:
        cust_name = invoice_data["company_name"]
        cust_type = "Company"
        customer_group = "Commercial"
    else:
        cust_name = full_name
        cust_type = "Individual"
        customer_group = "Individual"

    cust = frappe.new_doc("Customer")
    cust.customer_name = cust_name
    cust.customer_type = cust_type
    cust.customer_group = customer_group
    cust.territory = territory
    cust.flags.ignore_permissions = True
    cust.insert()

    contact = frappe.new_doc("Contact")
    contact.first_name = full_name
    contact.append("email_ids", {"email_id": email, "is_primary": 1})
    contact.append("links", {"link_doctype": "Customer", "link_name": cust.name})
    contact.flags.ignore_permissions = True
    contact.insert()

    _maybe_create_address(cust.name, cust_name, invoice_data)

    return cust.name


def _maybe_create_address(customer_name, address_title, invoice_data):
    if not invoice_data:
        return
    address_line1 = invoice_data.get("address_line1")
    if not address_line1:
        return
    city = invoice_data.get("city") or "-"
    country = invoice_data.get("country") or frappe.db.get_single_value("System Settings", "country") or "Germany"
    postcode = invoice_data.get("postcode") or ""

    addr = frappe.new_doc("Address")
    addr.address_title = address_title
    addr.address_type = "Billing"
    addr.address_line1 = address_line1
    if postcode:
        addr.pincode = postcode
    addr.city = city
    addr.country = country
    addr.is_primary_address = 1
    addr.append("links", {"link_doctype": "Customer", "link_name": customer_name})
    addr.flags.ignore_permissions = True
    addr.insert()


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
