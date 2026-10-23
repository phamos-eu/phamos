"""Events get an Attendance select (In person / Online) and a map pin instead of the pasted Map Link
(phamos/phamos#1665). Events whose venue is a link become online events; a map pin is read from the old
OpenStreetMap or Google Maps link where it holds coordinates. Street and postal code stay empty."""

import frappe


def execute():
	from phamos.marketing.location import IN_PERSON, ONLINE, coordinates_from_map_link, looks_like_url, point

	has_map_link = frappe.db.has_column("Marketing Content", "map_link")
	fields = "name, location, attendance_mode" + (", map_link" if has_map_link else "")
	for event in frappe.db.sql(f"select {fields} from `tabMarketing Content`", as_dict=True):
		if looks_like_url(event.location):
			frappe.db.set_value("Marketing Content", event.name, {"attendance_mode": ONLINE, "city": None},
				update_modified=False)
			continue
		values = {"attendance_mode": IN_PERSON} if event.attendance_mode != IN_PERSON else {}
		lat, lon = coordinates_from_map_link(event.get("map_link"))
		if lat is not None:
			values.update(geolocation=point(lat, lon), latitude=lat, longitude=lon)
		if values:
			frappe.db.set_value("Marketing Content", event.name, values, update_modified=False)
