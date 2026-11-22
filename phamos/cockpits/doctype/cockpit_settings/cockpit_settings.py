# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Settings of the cockpits, one tab per cockpit (#1932). They lived in phamos Settings before."""

import frappe
from frappe.model.document import Document

# Privacy mode of the HR Cockpit (#1839): shorter than this and the data is gone before it can be read.
MIN_PRIVACY_REVEAL_SECONDS = 10


# Ophice as the start page (#2077): Frappe's own "Default App" (System Settings) takes the first
# Apps-screen tile of the app it shows; while the switch is on, that is Ophice (see the two Ophice
# tiles in hooks.add_to_apps_screen).
OPHICE_DEFAULT_APP = "phamos"


def sync_ophice_start_page(on):
	"""Set or clear the standard default app, so everyone lands in Ophice after login."""
	# Uncached: a cached value can outlive a rollback and make this skip the write (#2089).
	current = frappe.db.get_single_value("System Settings", "default_app", cache=False)
	if on and current != OPHICE_DEFAULT_APP:
		frappe.db.set_single_value("System Settings", "default_app", OPHICE_DEFAULT_APP)
	elif not on and current == OPHICE_DEFAULT_APP:
		# Only what this switch set; another default app someone chose stays.
		frappe.db.set_single_value("System Settings", "default_app", "")
	# set_single_value skips the cached System Settings that frappe.get_system_settings() reads:
	# without this the login page keeps the old default until the cache is cleared.
	frappe.clear_document_cache("System Settings", "System Settings")


class CockpitSettings(Document):
	def on_update(self):
		# Only when the switch itself changed: saving a colour must not touch a default app that
		# was chosen some other way (review of the release).
		if self.has_value_changed("ophice_start_page"):
			sync_ophice_start_page(bool(self.ophice_start_page))
		# Company events of #1814 move once the General Management Department is known (#1949).
		# A site getting this release has no such department at migrate time, so the patch leaves
		# them for this save.
		from phamos.patches.v1_0 import move_company_events_to_department as move

		if self.general_management_department and move.has_company_events():
			moved = move.move_company_events()
			if moved:
				frappe.msgprint(
					frappe._("{0} company events moved to the General Management Department.").format(moved),
					alert=True,
				)

	def validate(self):
		seconds = self.human_resources_privacy_reveal_seconds
		if seconds is not None and seconds < MIN_PRIVACY_REVEAL_SECONDS:
			frappe.throw(
				frappe._("Privacy mode must show data for at least {0} seconds.").format(MIN_PRIVACY_REVEAL_SECONDS)
			)
