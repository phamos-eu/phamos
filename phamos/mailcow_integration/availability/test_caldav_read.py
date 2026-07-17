from datetime import timezone
from unittest import TestCase

from phamos.mailcow_integration.availability.caldav_read import _extract_dt_pairs


class TestCalDAVRead(TestCase):
    def test_timezone_dates_are_not_paired_with_event_end(self):
        ics = """BEGIN:VCALENDAR
BEGIN:VTIMEZONE
BEGIN:STANDARD
DTSTART:18930401T000000
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
DTSTART;TZID=Europe/Berlin:20260717T090000
DTEND;TZID=Europe/Berlin:20260717T100000
END:VEVENT
END:VCALENDAR"""

        intervals = _extract_dt_pairs(ics)

        self.assertEqual(len(intervals), 1)
        self.assertEqual(intervals[0][0].astimezone(timezone.utc).year, 2026)
        self.assertEqual(intervals[0][1].astimezone(timezone.utc).year, 2026)
