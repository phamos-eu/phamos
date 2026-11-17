# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Team calendar of the Project and Dev Action Panel shows leave without its type (#1840)."""

from types import SimpleNamespace
from unittest.mock import patch

from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

from phamos.phamos.page.project_action_panel import project_action_panel as pap


def _leave(**values):
	row = {
		"employee_name": "Anna Example",
		"from_date": getdate("2026-03-02"),
		"to_date": getdate("2026-03-03"),
		"leave_type": "Sick Leave",
		"half_day": 0,
		"half_day_date": None,
		"available_from_time": None,
		"available_to_time": None,
	}
	row.update(values)
	return SimpleNamespace(**row)


class TestTeamCalendarLeaves(FrappeTestCase):
	def _events(self, *leaves):
		with patch.object(pap.frappe, "get_all", return_value=list(leaves)) as get_all:
			events = pap.get_employee_leaves()
		return events, get_all.call_args.kwargs["fields"]

	def test_title_is_the_name_only(self):
		events, fields = self._events(_leave())
		self.assertEqual([e["title"] for e in events], ["Anna Example"])
		self.assertNotIn("leave_type", fields)

	def test_half_day_keeps_its_times_but_no_type(self):
		events, _ = self._events(
			_leave(
				half_day=1,
				from_date=getdate("2026-03-02"),
				to_date=getdate("2026-03-02"),
				half_day_date=getdate("2026-03-02"),
				available_from_time="09:00",
				available_to_time="12:00",
			)
		)
		self.assertEqual([e["title"] for e in events], ["Anna Example [09:00 - 12:00]"])
