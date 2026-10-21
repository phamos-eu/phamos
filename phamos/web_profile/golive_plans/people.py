"""Go-live People (phamos/phamos#1487, step 5a of #1492).

Old URLs: the overview `/people`, the old person pages `/<name>` (Employee Profile, 2023) and the
Web Pages below `people/`. A person's old URL only leads to their profile when the profile shows the
name (current team, alumni with consent). Anonymous people get no redirect at all: their old named
URL ends in "not found", so it is never linked to the anonymous page (phamos/phamos#1487).
"""

from phamos.web_profile.golive import DEFAULT_LANGUAGE, route_exists, section_plan
from phamos.web_profile.sections import get_items, section_url
from phamos.web_profile.utils import slugify


def plan():
	result = section_plan("people", ["people"])
	for item in get_items("people", DEFAULT_LANGUAGE):
		# Only phamos people had an old page of their own; anonymous ones keep none.
		if item.masked or item.data.get("party_type") != "Employee":
			continue
		url = f"{section_url('people', DEFAULT_LANGUAGE)}/{item.slug}"
		for source in (slugify(item.title), f"people/{slugify(item.title)}"):
			if not route_exists(source):
				result["redirects"].append((source, url))
	return result
