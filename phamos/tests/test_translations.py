# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Guards on phamos/translations: rows here also apply in Desk.

phamos loads after frappe and erpnext, so a row in phamos/translations/<lang>.csv
replaces their translation of the same source string everywhere, not only on
phamos's own pages.
"""

from frappe.tests.utils import FrappeTestCase
from frappe.translate import get_translations_from_apps


class TestDeskTranslationsStayIntact(FrappeTestCase):
	def test_lead_is_not_renamed_in_desk(self):
		"""A Web Profile row "Lead" → "Leitung" turned every CRM Lead label in
		German Desk into "Leitung". The department's lead is "Team lead"."""
		phamos = get_translations_from_apps("de", apps=["phamos"])
		self.assertIn(phamos.get("Lead"), (None, "Lead"))
		self.assertEqual(phamos.get("Team lead"), "Teamleitung")
