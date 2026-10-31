# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""The login Note announcing the Personal Cockpit (phamos/phamos#1769)."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate, today

from phamos.patches.v1_0 import announce_personal_cockpit as patch


class TestAnnouncePersonalCockpit(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Note", {"title": patch.TITLE})

	def tearDown(self):
		frappe.db.rollback()

	def test_creates_one_public_login_note_for_two_weeks(self):
		patch.execute()
		patch.execute()  # a second migrate must not post it twice
		notes = frappe.get_all(
			"Note",
			filters={"title": patch.TITLE},
			fields=["public", "notify_on_login", "notify_on_every_login", "expire_notification_on", "content"],
		)
		self.assertEqual(len(notes), 1)
		note = notes[0]
		self.assertEqual((note.public, note.notify_on_login, note.notify_on_every_login), (1, 1, 0))
		self.assertEqual(getdate(note.expire_notification_on), getdate(add_days(today(), 14)))
		self.assertIn('href="/personal-cockpit"', note.content)

	def test_every_user_sees_it_once(self):
		from frappe.desk.doctype.note.note import _get_unseen_notes, get_unseen_notes, mark_as_seen

		def unseen():
			_get_unseen_notes()  # what Frappe runs at login; it caches the list per user
			return [n.name for n in get_unseen_notes()]

		patch.execute()
		name = frappe.db.get_value("Note", {"title": patch.TITLE})
		self.assertIn(name, unseen())
		mark_as_seen(name)
		self.assertNotIn(name, unseen())
