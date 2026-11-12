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
	def test_lead_means_the_crm_lead(self):
		"""A Web Profile row "Lead" → "Leitung" turned every CRM Lead label in
		German Desk into "Leitung". "Lead" is the CRM Lead ("Interessent");
		the department's lead is "Team lead"."""
		phamos = get_translations_from_apps("de", apps=["phamos"])
		self.assertEqual(phamos.get("Lead"), "Interessent")
		self.assertEqual(phamos.get("Team lead"), "Teamleitung")
