import frappe

no_cache = 1


def get_context(context):
    req = frappe.local.request
    if req:
        selected_types = req.args.getlist("event_type")
    else:
        selected_types = []

    selected_city = frappe.form_dict.get("city", "")
    show_past     = frappe.form_dict.get("show_past", "")
    search        = frappe.form_dict.get("search", "")

    db_filters = {"published": 1}
    if selected_types:
        db_filters["event_type"] = ["in", selected_types]
    if selected_city:
        db_filters["city"] = selected_city
    if not show_past:
        db_filters["status"] = ["in", ["Upcoming", "Ongoing"]]

    events = frappe.get_all(
        "Phamos Event",
        filters=db_filters,
        fields=[
            "name", "title", "subtitle", "event_type", "status",
            "starts_on", "ends_on", "date_note", "location", "city",
            "image", "intro", "route",
            "going_count", "maybe_count", "not_going_count",
        ],
        order_by="starts_on asc",
    )

    if search:
        s = search.lower()
        events = [
            e for e in events
            if s in (e.title or "").lower()
            or s in (e.intro or "").lower()
            or s in (e.city or "").lower()
            or s in (e.location or "").lower()
        ]

    all_published = frappe.get_all(
        "Phamos Event",
        filters={"published": 1},
        fields=["event_type", "city"],
    )
    available_types  = sorted({e.event_type for e in all_published if e.event_type})
    available_cities = sorted({e.city for e in all_published if e.city})

    context.events           = events
    context.event_count      = len(events)
    context.available_types  = available_types
    context.available_cities = available_cities
    context.selected_types   = selected_types
    context.selected_city    = selected_city
    context.show_past        = show_past
    context.search           = search
    context.title            = "Events"
