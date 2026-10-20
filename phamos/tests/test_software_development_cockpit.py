# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""The Software Development cockpit (#1462) is wired like the other department cockpits."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.api import human_resources_spa
from phamos.api import software_development_spa as sd
from phamos.api.issue_raven import _spa_open_label, _spa_path_for


def _whitelisted(module):
	return {name for name, fn in vars(module).items() if callable(fn) and fn in frappe.whitelisted}


class TestSoftwareDevelopmentCockpit(FrappeTestCase):
	def test_config_fields_exist_in_phamos_settings(self):
		meta = frappe.get_meta("phamos Settings")
		self.assertTrue(meta.has_field(sd.CONFIG.department_field))
		self.assertTrue(meta.has_field(sd.CONFIG.project_field))

	def test_settings_keys_match_frontend_config(self):
		# software_development_frontend/src/config.js reads these keys from get_software_development_settings.
		self.assertEqual(sd.CONFIG.project_name_key, "software_development_timesheet_project_name")
		self.assertEqual(sd.CONFIG.project_count_key, "software_development_project_count")

	def test_exposes_the_same_endpoints_as_human_resources(self):
		# The shared spa_shared views call these by name, so a missing one breaks a screen.
		expected = {
			name.replace("get_human_resources_settings", sd.CONFIG.settings_method_name)
			for name in _whitelisted(human_resources_spa)
		}
		self.assertEqual(_whitelisted(sd), expected)

	def test_software_development_task_links_to_its_cockpit(self):
		depts = {"software_development_department": "Software Development"}
		with (
			patch("phamos.api.issue_raven._settings_dept", side_effect=depts.get),
			patch("frappe.db.get_value", return_value="Software Development"),
		):
			self.assertEqual(_spa_path_for("Task", "TASK-1"), "/software-development-cockpit/tasks/TASK-1")

	def test_open_label_names_software_development_cockpit(self):
		self.assertEqual(
			_spa_open_label("/software-development-cockpit/tasks/TASK-1"),
			"Open in Software Development Cockpit",
		)
