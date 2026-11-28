# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Plain text of every website copy, for the documentation search (phamos/phamos#2046).

The sync fills Bookstack Page.search_text from now on; copies made before get it here, from
the HTML already stored. No network.
"""

import frappe

from phamos.bookstack_integration.content import plain_text


def execute():
	for page in frappe.get_all("Bookstack Page", filters={"html": ["is", "set"]}, fields=["name", "html"]):
		frappe.db.set_value("Bookstack Page", page.name, "search_text", plain_text(page.html), update_modified=False)
