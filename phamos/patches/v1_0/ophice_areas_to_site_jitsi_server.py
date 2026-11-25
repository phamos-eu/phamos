# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Ophice meeting areas on meet.jit.si move to the site's Jitsi server (phamos/phamos#2108).

meet.jit.si makes a new room wait for a logged-in moderator and ends embedded calls after
5 minutes. Jitsi rooms are only names, so each area keeps its room and only the server changes:
https://meet.jit.si/OurStandup becomes https://<site server>/OurStandup. A site that lists
meet.jit.si as allowed (site config) keeps its areas there.
"""

import frappe

from phamos.api.ophice import AREA_DOCTYPE, LEGACY_JITSI_DOMAINS, _allowed_jitsi_domains, _jitsi_domain


def execute():
	if not frappe.db.table_exists(AREA_DOCTYPE):
		return
	target = _jitsi_domain()
	allowed = _allowed_jitsi_domains()
	legacy = [domain for domain in LEGACY_JITSI_DOMAINS if domain not in allowed]
	if not legacy:
		return
	areas = frappe.get_all(AREA_DOCTYPE, filters={"jitsi_domain": ["in", legacy]}, fields=["name", "jitsi_room"])
	for area in areas:
		frappe.db.set_value(
			AREA_DOCTYPE,
			area.name,
			{"jitsi_domain": target, "meeting_url": f"https://{target}/{area.jitsi_room}" if area.jitsi_room else ""},
			update_modified=False,
		)
