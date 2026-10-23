"""Where an event takes place (phamos/phamos#1665).

``attendance_mode`` says whether an event is in person or online. Like Apple Calendar and other .ics
planners, ``location`` holds either the venue (in person) or the meeting link (online). An in-person
venue has a structured address and a map pin; the pin comes from OpenStreetMap's Nominatim geocoder
or is set by hand on the form's map.

The meeting link is private: it reaches registered attendees only (ticket emails and their calendar
file), never the website's item data.
"""

import json
import re
import time
from urllib.parse import unquote

import frappe
from frappe import _
from frappe.utils import flt

ONLINE = "Online"
IN_PERSON = "In person"
URL = re.compile(r"^\s*(https?://|www\.)", re.IGNORECASE)
HTTPS = re.compile(r"^https://[^\s/?#]+\.[^\s/?#]+\S*$", re.IGNORECASE)
ADDRESS_FIELDS = ("street", "postal_code", "city", "country")
NOMINATIM_URL = "https://nominatim.openstreetmap.org"
NOMINATIM_INTERVAL = 1.0  # seconds between requests (Nominatim usage policy)


def is_online(doc):
	return doc.get("attendance_mode") == ONLINE


def looks_like_url(value):
	return bool(value and URL.match(value))


def is_https_url(value):
	return bool(value and HTTPS.match(value.strip()))


def address_line(doc, with_venue=True):
	""""Hotel Adlon, Unter den Linden 77, 10117 Berlin": one line, as calendar apps expect it."""
	return ", ".join(filter(None, [
		doc.get("location") if with_venue else None,
		doc.get("street"),
		" ".join(filter(None, [doc.get("postal_code"), doc.get("city")])),
	]))


# --- map pin ----------------------------------------------------------------------------------------------


def point(latitude, longitude):
	"""GeoJSON for Frappe's Geolocation field: one point (GeoJSON order is longitude, latitude)."""
	return json.dumps({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {},
		"geometry": {"type": "Point", "coordinates": [flt(longitude), flt(latitude)]}}]})


def coordinates(geojson):
	"""(latitude, longitude) of the first point in a Geolocation value, else (None, None)."""
	try:
		data = json.loads(geojson) if isinstance(geojson, str) else geojson
	except ValueError:
		return None, None
	for feature in (data or {}).get("features") or []:
		geometry = feature.get("geometry") or {}
		if geometry.get("type") == "Point" and len(geometry.get("coordinates") or []) >= 2:
			lon, lat = geometry["coordinates"][:2]
			return flt(lat), flt(lon)
	return None, None


def coordinates_from_map_link(url):
	"""(latitude, longitude) from an OpenStreetMap or Google Maps share URL, else (None, None)."""
	url = unquote(url or "")
	for pattern in (r"mlat=(-?\d+\.\d+).*?mlon=(-?\d+\.\d+)",  # openstreetmap.org/?mlat=..&mlon=..
			r"#map=\d+/(-?\d+\.\d+)/(-?\d+\.\d+)",  # openstreetmap.org/#map=zoom/lat/lon
			r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)",  # Google: the place itself
			r"@(-?\d+\.\d+),(-?\d+\.\d+)",  # Google: the map's centre
			r"[?&](?:q|ll|query)=(-?\d+\.\d+),\s*(-?\d+\.\d+)"):
		match = re.search(pattern, url)
		if match:
			lat, lon = flt(match.group(1)), flt(match.group(2))
			if -90 <= lat <= 90 and -180 <= lon <= 180:
				return lat, lon
	return None, None


# --- geocoding (OpenStreetMap Nominatim) ------------------------------------------------------------------


def geocode(street=None, postal_code=None, city=None, country=None):
	"""{"latitude", "longitude", "label"} for an address, or None when Nominatim finds nothing or is
	unreachable. Server-side only, with our own User-Agent and at most one request per second. The
	base URL can point at a self-hosted Nominatim (site config ``nominatim_url``)."""
	if not (street or postal_code or city):
		return None
	params = {"format": "jsonv2", "limit": 1, "addressdetails": 0,
		"street": street or "", "postalcode": postal_code or "", "city": city or ""}
	if country:
		code = frappe.db.get_value("Country", country, "code")
		if code:
			params["countrycodes"] = code.lower()
		else:
			params["country"] = country
	try:
		results = _search({k: v for k, v in params.items() if v != ""})
	except Exception:
		frappe.log_error(title="Event location: geocoding failed", message=frappe.get_traceback())
		return None
	if not results:
		return None
	return {"latitude": flt(results[0]["lat"]), "longitude": flt(results[0]["lon"]),
		"label": results[0].get("display_name")}


def _search(params):
	"""Nominatim's /search. Tests never reach the network: they patch this function."""
	import requests

	if frappe.flags.in_test:
		return []
	_wait_for_turn()
	response = requests.get(f"{(frappe.conf.get('nominatim_url') or NOMINATIM_URL).rstrip('/')}/search",
		params=params, timeout=8,
		headers={"User-Agent": f"phamos-events/1.0 ({frappe.utils.get_url()})", "Accept-Language": "de,en"})
	response.raise_for_status()
	return response.json()


def _wait_for_turn():
	key = "phamos:nominatim_last_request"
	last = flt(frappe.cache.get_value(key))
	wait = last + NOMINATIM_INTERVAL - time.time()
	if wait > 0:
		time.sleep(min(wait, NOMINATIM_INTERVAL))
	frappe.cache.set_value(key, time.time(), expires_in_sec=60)


@frappe.whitelist()
def find_on_map(street=None, postal_code=None, city=None, country=None):
	"""The form's "Find on Map" button."""
	frappe.has_permission("Marketing Content", "write", throw=True)
	result = geocode(street, postal_code, city, country)
	if not result:
		frappe.throw(_("This address was not found on OpenStreetMap. Please check it, or set the pin on the map by hand."),
			title=_("Not found"))
	return result
