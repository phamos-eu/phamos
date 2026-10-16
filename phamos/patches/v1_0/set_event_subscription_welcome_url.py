"""Event Email Groups returned confirmed subscribers to the event page with "?subscribed=1", where a small
note was easy to miss. They now go to the confirmation page (/de/anmeldung-bestaetigt)."""

import frappe


def execute():
	from phamos.marketing.doctype.marketing_content.marketing_content import subscription_confirmed_url

	for event in frappe.get_all("Marketing Content", filters={"email_group": ["is", "set"], "route": ["is", "set"]},
			fields=["email_group", "route"]):
		welcome_url = frappe.db.get_value("Email Group", event.email_group, "welcome_url")
		if welcome_url is not None and (not welcome_url or welcome_url.endswith("?subscribed=1")):
			frappe.db.set_value("Email Group", event.email_group, "welcome_url",
				subscription_confirmed_url(event.route), update_modified=False)
