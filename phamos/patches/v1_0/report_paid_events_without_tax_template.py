"""List the published paid events without an Item Tax Template (phamos/phamos#1710). Changes nothing.

Since #1710 ticket sales stay closed for a paid event without an Item Tax Template: the tax rate shown on the
page and the tax on the Sales Order both come from it. The events listed here stop selling until an editor
adds one, so read this output before the deploy.
"""

import frappe


def execute():
	events = frappe.get_all("Marketing Content", filters={"ticket_item": ["is", "set"], "published": 1,
		"item_tax_template": ["in", ["", None]]}, fields=["name", "title", "registration_open"], order_by="name")
	if not events:
		print("Paid events without an Item Tax Template: none.")
		return
	print(f"Paid events without an Item Tax Template ({len(events)}): ticket sales stay closed until one is set.")
	for event in events:
		print(f"- {event.name}: {event.title}{' (registration open)' if event.registration_open else ''}")
