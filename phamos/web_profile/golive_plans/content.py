"""Go-live content pages (phamos/phamos#1539, step 5i of #1492).

The content pages are Web Pages in two languages (`de/preise`, `en/pricing`, linked with *Translation
Of*, phamos/phamos#1502). Old URLs without a language (`/preise`, `/pricing`, `/services/support`) lead
to the German page, the default language. Old Web Pages without a language prefix that have a
translated page with the same title are unpublished. Old pages without a match are only listed in
the report: a person decides about them (e.g. the home page).
"""

import frappe

from phamos.web_profile.golive import DEFAULT_LANGUAGE, route_exists
from phamos.web_profile.i18n import LANGUAGES
from phamos.web_profile.utils import slugify

# Old overviews of the profile sections: their go-live plans handle them.
SECTION_PREFIXES = ("people", "departments", "teams", "modules", "implementations", "industries",
	"references", "referenzen", "customers", "partnerships", "partnerschaften", "partners")


def plan():
	pages = frappe.get_all("Web Page", fields=["name", "route", "title", "language", "translation_of", "published"])
	translated = [p for p in pages if p.language in LANGUAGES and (p.route or "").split("/")[0] in LANGUAGES]
	# German page of each translation group: the master itself or the page an English one points to.
	german = {p.name: p for p in translated if p.language == DEFAULT_LANGUAGE}
	target = {}
	for page in translated:
		master = german.get(page.translation_of) or german.get(page.name)
		if master and master.published:
			target[page.name] = "/" + master.route

	redirects, unpublish, notes = [], [], []
	for page in translated:
		if page.name not in target:
			continue
		old = page.route.split("/", 1)[1] if "/" in page.route else ""
		if old and not route_exists(old):
			redirects.append((old, target[page.name]))

	by_title = {slugify(p.title): target[p.name] for p in translated if p.name in target}
	for page in pages:
		route = (page.route or "").strip("/")
		if not route or route.split("/")[0] in LANGUAGES or route.split("/")[0] in SECTION_PREFIXES:
			continue
		match = by_title.get(slugify(page.title))
		if match:
			redirects.append((route, match))
			unpublish.append(page.name)
		elif page.published:
			notes.append(f"{route}: old page without a translated counterpart, left as it is")
	return {"redirects": redirects, "unpublish": unpublish, "notes": notes}
