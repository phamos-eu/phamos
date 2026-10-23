"""Go-live Events (Marketing Content on the Web Profile engine).

Old URLs: the overview ``/events``, each event at ``/events/<old route>`` (``legacy_route``, kept by the
patch move_marketing_content_to_web_profile) and the retired guest web form ``/event-registration``.
Published events go to their new page, unpublished ones to the overview. Keep these redirects for good:
newsletters and search results link the old URLs.
"""

import frappe

from phamos.web_profile.golive import DEFAULT_LANGUAGE, section_plan
from phamos.web_profile.sections import item_url, section_url


def plan():
	result = section_plan("events", ["events"], extra_sources=("event-registration", "event-registration/new"))
	listing = section_url("events", DEFAULT_LANGUAGE)
	seen = {source for source, _target in result["redirects"]}
	for r in frappe.get_all("Marketing Content", fields=["route", "legacy_route", "published"]):
		old = (r.legacy_route or "").strip("/")
		sources = {old, f"events/{old.removeprefix('events/')}"} if old else {f"events/{r.route}"}
		target = item_url("events", r.route, DEFAULT_LANGUAGE) if r.published else listing
		for source in sorted(sources):
			if source and source not in seen and source != "events":
				result["redirects"].append((source, target))
				seen.add(source)
		if not r.published:
			result["notes"].append(f"{old or r.route}: not published, goes to the overview")
	return result
