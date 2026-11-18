# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

""""Open in Cockpit" on the Desk Issue form (#1957): which cockpits fit, best fit first."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.api import issue_cockpits as ic

# Department per cockpit (Cockpit Settings), keyed by CockpitConfig.department_field.
DEPARTMENTS = {
	"software_development_department": "Software Development",
	"sales_department": "Sales",
	"accounting_department": "Accounts",
}


# One Apps-screen entry, for the module-loading tests.
APPS = [{"name": "sales_spa", "route": "/sales-cockpit"}]


def _department(config):
	return DEPARTMENTS.get(config.department_field)


def _issue(name="ISS-TEST-1957", owner="someone-else@example.com", custom_department=None, project=None):
	return frappe._dict(
		doctype="Issue",
		name=name,
		owner=owner,
		custom_department=custom_department,
		project=project,
	)


class TestIssueCockpits(FrappeTestCase):
	def _fit(self, doc, assigned=False, project_department=None, can_open=lambda module: True):
		modules = ic._cockpit_modules()
		get_value = frappe.db.get_value

		def project_lookup(doctype, *args, **kwargs):
			# Only the Project → department lookup in _issue_in_scope is faked.
			if doctype == "Project":
				return project_department
			return get_value(doctype, *args, **kwargs)

		with (
			patch("phamos.api.department_cockpit._get_department", side_effect=_department),
			patch("phamos.api.department_cockpit._is_assigned", return_value=assigned),
			patch.object(frappe.db, "get_value", side_effect=project_lookup),
			patch.object(ic, "_cockpit_modules", return_value=modules),
		):
			patches = [
				patch.object(module, "check_app_permission", return_value=can_open(module))
				for module, _route in modules
			]
			for p in patches:
				p.start()
			try:
				return ic.cockpits_for_issue(doc)
			finally:
				for p in patches:
					p.stop()

	def test_every_cockpit_with_a_config_is_listed(self):
		routes = {route for _module, route in ic._cockpit_modules()}
		self.assertIn("/personal-cockpit", routes)
		self.assertIn("/software-development-cockpit", routes)
		self.assertNotIn("/scan", routes)

	def test_issue_in_no_scope_has_no_cockpit(self):
		self.assertEqual(self._fit(_issue()), [])

	def test_assigned_issue_opens_in_personal_cockpit(self):
		self.assertEqual(
			self._fit(_issue(), assigned=True),
			[{"label": "Personal", "url": "/personal-cockpit/issues/list/ISS-TEST-1957"}],
		)

	def test_own_issue_opens_in_personal_cockpit(self):
		doc = _issue(owner=frappe.session.user)
		self.assertEqual([c["label"] for c in self._fit(doc)], ["Personal"])

	def test_department_issue_opens_in_its_department_cockpit(self):
		doc = _issue(custom_department="Sales")
		self.assertEqual(
			self._fit(doc),
			[{"label": "Sales", "url": "/sales-cockpit/issues/list/ISS-TEST-1957"}],
		)

	def test_order_is_personal_then_issue_department_then_project_department(self):
		# Accounting comes before Software Development in hooks; the Issue's own department wins.
		doc = _issue(custom_department="Software Development", project="PROJ-1957")
		labels = [c["label"] for c in self._fit(doc, assigned=True, project_department="Accounts")]
		self.assertEqual(labels, ["Personal", "Software Development", "Accounting"])

	def test_cockpit_the_user_cannot_open_is_left_out(self):
		doc = _issue(custom_department="Sales")
		fit = self._fit(doc, can_open=lambda module: module.__name__ != "phamos.api.sales_spa")
		self.assertEqual(fit, [])

	def test_issue_name_is_url_encoded(self):
		doc = _issue(name="ISS 1/2")
		self.assertEqual(
			self._fit(doc, assigned=True)[0]["url"],
			"/personal-cockpit/issues/list/ISS%201%2F2",
		)

	def test_endpoint_checks_read_permission(self):
		doc = frappe.get_doc({"doctype": "Issue", "subject": "Open in Cockpit #1957"})
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
		frappe.set_user("Guest")
		try:
			with self.assertRaises(frappe.PermissionError):
				ic.get_issue_cockpits(doc.name)
		finally:
			frappe.set_user("Administrator")

	def test_broken_cockpit_module_raises_instead_of_vanishing(self):
		broken = ModuleNotFoundError("No module named 'missing_dependency'", name="missing_dependency")
		with (
			patch.object(ic.frappe, "get_hooks", return_value=APPS),
			patch.object(ic.frappe, "get_module", side_effect=broken),
		):
			with self.assertRaises(ModuleNotFoundError):
				ic._cockpit_modules()

	def test_apps_screen_entry_without_api_module_is_skipped(self):
		def get_module(name):
			raise ModuleNotFoundError(f"No module named '{name}'", name=name)

		with (
			patch.object(ic.frappe, "get_hooks", return_value=APPS),
			patch.object(ic.frappe, "get_module", side_effect=get_module),
		):
			self.assertEqual(ic._cockpit_modules(), [])
