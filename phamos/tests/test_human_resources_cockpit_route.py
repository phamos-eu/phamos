# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""The HR cockpit lives at /human-resources-cockpit; old /hr-cockpit links redirect there."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.website.path_resolver import resolve_redirect

from phamos.api.issue_raven import _spa_open_label, _spa_path_for


class TestHumanResourcesCockpitRoute(FrappeTestCase):
	def test_hr_task_links_to_human_resources_cockpit(self):
		depts = {"human_resources_department": "Human Resources"}
		with (
			patch("phamos.api.issue_raven._settings_dept", side_effect=depts.get),
			patch("frappe.db.get_value", return_value="Human Resources"),
		):
			self.assertEqual(_spa_path_for("Task", "TASK-1"), "/human-resources-cockpit/tasks/TASK-1")

	def test_open_label_names_human_resources_cockpit(self):
		self.assertEqual(
			_spa_open_label("/human-resources-cockpit/tasks/TASK-1"), "Open in Human Resources Cockpit"
		)

	def test_old_route_redirects_permanently(self):
		cases = {
			"hr-cockpit": "/human-resources-cockpit",
			"hr-cockpit/tasks/TASK-1": "/human-resources-cockpit/tasks/TASK-1",
			"hr_spa": "/human-resources-cockpit",
		}
		for old, new in cases.items():
			with self.subTest(path=old):
				frappe.cache.hdel("website_redirects", old)
				with self.assertRaises(frappe.Redirect) as ctx:
					resolve_redirect(old)
				self.assertEqual(frappe.flags.redirect_location, new)
				self.assertEqual(ctx.exception.http_status_code, 301)

	def test_lookalike_route_is_not_redirected(self):
		frappe.cache.hdel("website_redirects", "hr-cockpit-archive")
		self.assertIsNone(resolve_redirect("hr-cockpit-archive"))
