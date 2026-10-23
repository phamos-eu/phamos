"""Events get an Attendance select (In person / Online) and a map pin instead of the pasted Map Link
(phamos/phamos#1665). Events whose venue is a web link become online events; a map pin is read from the old
OpenStreetMap or Google Maps link where it holds coordinates. Street and postal code stay empty.

Safe to run twice: nothing is cleared (the city of an online event stays until the event is next saved), and
a pin that is already set is never replaced."""

import re

import frappe

# Only a real link makes an event online. "www.hotel.de" may be a venue's name; the form asks the editor.
LINK = re.compile(r"^\s*https?://", re.IGNORECASE)


def execute():
	from phamos.marketing.location import IN_PERSON, ONLINE, coordinates_from_map_link, point

	has_map_link = frappe.db.has_column("Marketing Content", "map_link")
	fields = "name, location, attendance_mode, geolocation" + (", map_link" if has_map_link else "")
	for event in frappe.db.sql(f"select {fields} from `tabMarketing Content`", as_dict=True):
		mode = ONLINE if event.location and LINK.match(event.location) else IN_PERSON
		values = {"attendance_mode": mode} if event.attendance_mode != mode else {}
		if mode == IN_PERSON and not event.geolocation:
			lat, lon = coordinates_from_map_link(event.get("map_link"))
			if lat is not None:
				values.update(geolocation=point(lat, lon), latitude=lat, longitude=lon)
		if values:
			frappe.db.set_value("Marketing Content", event.name, values, update_modified=False)
