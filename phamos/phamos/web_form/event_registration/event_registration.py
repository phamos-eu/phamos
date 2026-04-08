import frappe
from frappe.utils import get_datetime


def get_context(context):
    event_name = (
        frappe.local.request.args.get("event")
        or frappe.form_dict.get("event")
    )
    if not event_name:
        return

    try:
        event = frappe.get_doc("Marketing Content", event_name)
    except Exception:
        return

    context.title = f"Register — {event.title}"

    # Pre-set the event field default so it's populated before JS runs
    for field in context.web_form_doc.get("web_form_fields", []):
        if field.get("fieldname") == "event":
            field["default"] = event_name
            break

    # Date line
    date_text = ""
    if event.starts_on:
        dt = get_datetime(event.starts_on)
        date_text = dt.strftime("%B %d, %Y · %H:%M")
    elif event.date_note:
        date_text = event.date_note

    # Location line
    location_parts = [p for p in [event.location, event.city] if p]
    location_text = " · ".join(location_parts)

    image_html = ""
    if event.image:
        safe_title = frappe.utils.escape_html(event.title)
        image_html = (
            f'<img src="{event.image}" alt="{safe_title}" '
            f'style="width:100%;height:140px;object-fit:cover;display:block;">'
        )

    date_row = ""
    if date_text:
        date_row = (
            '<div class="pe-wf-meta-row">'
            '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor"'
            ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
            '<rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>'
            '<line x1="16" y1="2" x2="16" y2="6"/>'
            '<line x1="8" y1="2" x2="8" y2="6"/>'
            '<line x1="3" y1="10" x2="21" y2="10"/></svg>'
            f"{frappe.utils.escape_html(date_text)}</div>"
        )

    location_row = ""
    if location_text:
        location_row = (
            '<div class="pe-wf-meta-row">'
            '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor"'
            ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
            '<path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/>'
            '<circle cx="12" cy="10" r="3"/></svg>'
            f"{frappe.utils.escape_html(location_text)}</div>"
        )

    safe_title = frappe.utils.escape_html(event.title)

    context.introduction_text = f"""
<style>
  :root {{ --pe-accent: #8b1a2e; --pe-border: #e8e2d9; --pe-muted: #78716c; }}
  .page-head .title-area, .page-breadcrumbs {{ display: none !important; }}
  .web-form-wrapper {{ max-width: 560px; margin: 2rem auto; padding: 0 1rem; }}
  .pe-wf-card {{
    border: 1.5px solid var(--pe-border); border-radius: 10px;
    overflow: hidden; margin-bottom: 1.8rem; background: #faf8f5;
  }}
  .pe-wf-card-body {{ padding: .9rem 1rem; }}
  .pe-wf-title {{
    font-size: 1.15rem; font-weight: 800; color: #1c1917;
    letter-spacing: -.02em; margin: 0 0 .5rem; line-height: 1.25;
  }}
  .pe-wf-meta {{ display: flex; flex-direction: column; gap: .3rem; }}
  .pe-wf-meta-row {{
    display: flex; align-items: center; gap: .45rem;
    font-size: .8rem; color: var(--pe-muted);
  }}
  .pe-wf-meta-row svg {{ flex-shrink: 0; }}
  .frappe-control[data-fieldname="event"] {{ display: none !important; }}
  .web-form-container .frappe-control label,
  .web-form-container .form-group label {{
    font-weight: 600; font-size: .85rem; color: #1c1917;
  }}
  .web-form-container .form-control,
  .web-form-container input[type=text],
  .web-form-container input[type=email],
  .web-form-container input[type=number],
  .web-form-container textarea {{
    border: 1.5px solid var(--pe-border) !important;
    border-radius: 7px !important;
    font-size: .88rem !important;
  }}
  .web-form-container .form-control:focus,
  .web-form-container input:focus,
  .web-form-container textarea:focus {{
    border-color: var(--pe-accent) !important;
    box-shadow: 0 0 0 3px rgba(139,26,46,.1) !important;
    outline: none !important;
  }}
  .web-form-footer .btn-primary,
  .web-form-actions .btn-primary {{
    background: var(--pe-accent) !important;
    border-color: var(--pe-accent) !important;
    border-radius: 7px !important;
    font-weight: 700 !important;
    padding: .6rem 2rem !important;
    font-size: .9rem !important;
    letter-spacing: .02em;
  }}
  .web-form-footer .btn-primary:hover,
  .web-form-actions .btn-primary:hover {{ opacity: .88 !important; }}
</style>
<div class="pe-wf-card">
  {image_html}
  <div class="pe-wf-card-body">
    <h2 class="pe-wf-title">{safe_title}</h2>
    <div class="pe-wf-meta">
      {date_row}
      {location_row}
    </div>
  </div>
</div>
"""
