"""Section registry and item loaders for the Web Profile pages.

A *section* is one public area of the site (people, departments, ...). For each section this
module declares its URL slugs and filters, and turns its Web Profile records into display
*items*: the plain dicts every tile, filter count and profile page is rendered from.

Privacy is applied here, once, before anything reaches a template: anonymous alumni and
unapproved customers never carry a name, photo or named URL in their item.
"""

from datetime import date

import frappe
from frappe import _
from frappe.utils import getdate

from phamos.web_profile.i18n import localized
from phamos.web_profile.icons import flag_url, module_icon
from phamos.web_profile.socials import detect_platform, normalize_url, social_link
from phamos.web_profile.utils import initials, slugify

ORGANIZATION = {"@type": "Organization", "name": "phamos GmbH", "url": "https://phamos.eu"}
CACHE_KEY = "web_profile_items"
CACHE_SECONDS = 600

# Untranslated strings; templates and listing.py pass them through _() for the request language.
SECTIONS = {
	"people": {
		"doctype": "Person Web Profile",
		"slugs": {"en": "people", "de": "personen"},
		"title": "People",
		"intro": "The people behind our projects: our team, former colleagues, and the customers and partners we work with eye to eye.",
		"noun": ("person", "people"),
		"search_placeholder": "Search people",
		"facets": [
			{"key": "status", "label": "Relationship", "type": "bands",
				"options": [("current", "Our team"), ("partners", "Customers & partners"), ("alumni", "Alumni")]},
			{"key": "organization", "label": "Organization", "type": "multi"},
			{"key": "department", "label": "Department", "type": "multi"},
			{"key": "team", "label": "Team", "type": "multi"},
			{"key": "designation", "label": "Designation", "type": "multi"},
			{"key": "module", "label": "Module expertise", "type": "multi"},
			{"key": "tenure", "label": "Time at phamos", "type": "range", "unit": "years"},
			{"key": "language", "label": "Language", "type": "multi"},
		],
		"sorts": [("manual", "Recommended"), ("name", "Name A–Z"), ("tenure", "Time at phamos")],
	},
	"departments": {
		"doctype": "Department Web Profile",
		"slugs": {"en": "departments", "de": "abteilungen"},
		"title": "Departments",
		"intro": "Small specialist departments that stay close to customers.",
		"noun": ("department", "departments"),
		"search_placeholder": "Search departments",
		"facets": [
			{"key": "size", "label": "Department size", "type": "range", "unit": "people"},
		],
		"sorts": [("manual", "Recommended"), ("name", "Name A–Z"), ("size", "Largest first")],
	},
	"teams": {
		"doctype": "Team Web Profile",
		"slugs": {"en": "teams", "de": "teams"},
		"title": "Teams",
		"intro": "Delivery teams that take an implementation from first workshop to go-live.",
		"noun": ("team", "teams"),
		"search_placeholder": "Search teams",
		"facets": [
			{"key": "size", "label": "Team size", "type": "range", "unit": "members"},
			{"key": "founded", "label": "Founded", "type": "range"},
		],
		"sorts": [("manual", "Recommended"), ("name", "Name A–Z"), ("size", "Largest first")],
	},
	"modules": {
		"doctype": "Module Web Profile",
		"slugs": {"en": "modules", "de": "module"},
		"title": "Modules",
		"intro": "The ERPNext modules we introduce, step by step and one module at a time.",
		"noun": ("module", "modules"),
		"search_placeholder": "Search modules",
		"facets": [
			{"key": "complexity", "label": "Complexity", "type": "bands",
				"options": [("Low", "Low"), ("Medium", "Medium"), ("High", "High"), ("Critical", "Critical")]},
			{"key": "industry", "label": "Industry", "type": "multi"},
		],
		"sorts": [("manual", "Recommended"), ("name", "Name A–Z")],
	},
	"implementations": {
		"doctype": "Implementation Web Profile",
		"slugs": {"en": "implementations", "de": "implementierungen"},
		"title": "Implementations",
		"intro": "ERPNext projects we have delivered or are delivering right now.",
		"noun": ("implementation", "implementations"),
		"search_placeholder": "Search implementations",
		"facets": [
			{"key": "industry", "label": "Industry", "type": "multi"},
			{"key": "module", "label": "Module", "type": "multi"},
			{"key": "team", "label": "Team", "type": "multi"},
			{"key": "year", "label": "Start year", "type": "range"},
		],
		"sorts": [("manual", "Recommended"), ("newest", "Newest first"), ("name", "Name A–Z")],
	},
	"industries": {
		"doctype": "Industry Web Profile",
		"slugs": {"en": "industries", "de": "branchen"},
		"title": "Industries",
		"intro": "Industries we know well, and the modules that matter most in each.",
		"noun": ("industry", "industries"),
		"search_placeholder": "Search industries",
		"facets": [
			{"key": "module", "label": "Module", "type": "multi"},
		],
		"sorts": [("manual", "Recommended"), ("name", "Name A–Z")],
	},
	"customers": {
		"doctype": "Stakeholder Web Profile",
		"stakeholder_type": "Customer",
		"slugs": {"en": "customers", "de": "kunden"},
		"title": "Customers",
		"intro": "Companies we work with on eye level, and the ERPNext projects we delivered together.",
		"noun": ("customer", "customers"),
		"search_placeholder": "Search customers",
		"facets": [
			{"key": "industry", "label": "Industry", "type": "multi"},
			{"key": "module", "label": "Module", "type": "multi"},
			{"key": "team", "label": "Team", "type": "multi"},
			{"key": "since", "label": "Customer since", "type": "range"},
		],
		"sorts": [("manual", "Recommended"), ("name", "Name A–Z"), ("newest", "Newest first")],
	},
	"partners": {
		"doctype": "Stakeholder Web Profile",
		"stakeholder_type": "Partner",
		"slugs": {"en": "partners", "de": "partner"},
		"title": "Partners",
		"intro": "Companies we work with as partners: technology, hosting and implementation partners.",
		"noun": ("partner", "partners"),
		"search_placeholder": "Search partners",
		"facets": [
			{"key": "industry", "label": "Industry", "type": "multi"},
		],
		"sorts": [("manual", "Recommended"), ("name", "Name A–Z")],
	},
}

# Website sections backed by the Stakeholder Web Profile (one per stakeholder type).
STAKEHOLDER_SECTIONS = ("customers", "partners")


# --- URLs -----------------------------------------------------------------------------------------


def section_url(section, lang):
	return f"/{lang}/{SECTIONS[section]['slugs'][lang]}"


def item_url(section, slug, lang):
	return f"{section_url(section, lang)}/{slug}"


# --- item cache -----------------------------------------------------------------------------------


def get_items(section, lang):
	"""All published items of a section, in display form for ``lang`` (cached, invalidated on save)."""
	memo = getattr(frappe.local, "web_profile_items", None)
	if memo is None:
		memo = frappe.local.web_profile_items = {}  # per-request memo; frappe.local is reset per request
	if (section, lang) in memo:
		return memo[(section, lang)]

	cache_field = f"{section}:{lang}"
	items = frappe.cache.hget(CACHE_KEY, cache_field)
	if items is None:
		items = LOADERS[section](lang)
		frappe.cache.hset(CACHE_KEY, cache_field, items)
		frappe.cache.expire(CACHE_KEY, CACHE_SECONDS)
	items = [frappe._dict(i) for i in items]
	memo[(section, lang)] = items
	return items


def find_item(section, slug, lang):
	"""The published item with this URL slug, or None. Every record has one neutral URL from its
	creation, the same for its named and anonymous page (phamos/phamos#1512)."""
	return next((item for item in get_items(section, lang) if item.slug == slug), None)


def _item(section, record, lang, title, slug, *, subtitle="", image=None, masked=False):
	return {
		"section": section,
		"name": record.name,
		"slug": slug,
		"url": item_url(section, slug, lang),
		"title": title,
		"subtitle": subtitle,
		"image": None if masked else image,
		"icon": None,
		"socials": [],
		"numbers": {},  # values of the "range" facets (min/max sliders)
		"initials": "–" if masked else initials(title),
		"masked": masked,
		"chips": [],
		"facets": {},
		"labels": {},
		"sort": {"manual": [record.get("sort_order") or 0, (title or "").lower()], "name": (title or "").lower()},
		"search": "",
		"summary": "",
		"body": "",
		"data": {},
	}


def _facet(item, key, value, label):
	if value in (None, ""):
		return
	value = str(value)
	item["facets"].setdefault(key, [])
	if value not in item["facets"][key]:
		item["facets"][key].append(value)
	item["labels"].setdefault(key, {})[value] = label


def _published(doctype, fields):
	return attach_texts(doctype,
		frappe.get_all(doctype, filters={"published": 1}, fields=["name", "route", "sort_order", "image", *fields]))


def attach_texts(doctype, records):
	"""Give every record its "Web Profile Content" rows as ``record.texts`` ({language: row}),
	read by i18n.localized. One query per doctype instead of one per record."""
	texts = {}
	names = [r.name for r in records]
	if names:
		for row in frappe.get_all("Web Profile Content", filters={"parenttype": doctype, "parent": ["in", names]},
				fields=["parent", "language", "title", "summary", "content"]):
			texts.setdefault(row.parent, {})[row.language] = row
	for r in records:
		r.texts = texts.get(r.name, {})
	return records


def _industry_titles(lang):
	"""{Industry Type: name shown in ``lang``}: the title of the industry's text row in that language,
	else the Industry Type name (translated by Frappe)."""
	records = attach_texts("Industry Web Profile", frappe.get_all("Industry Web Profile", fields=["name", "industry"]))
	return {r.industry: localized(r, "title", lang, fallback=False) or _(r.industry) for r in records}


def _children(child_doctype, parent_doctype, field):
	rows = frappe.get_all(
		child_doctype, filters={"parenttype": parent_doctype}, fields=["parent", field], order_by="idx asc"
	)
	out = {}
	for row in rows:
		out.setdefault(row.parent, []).append(row[field])
	return out


def _profile_map(doctype, link_field, title_field):
	"""{source name: (slug, title)} of published profiles, used to turn links into facet values."""
	return {
		r[link_field]: (r.route, r[title_field])
		for r in frappe.get_all(doctype, filters={"published": 1}, fields=[link_field, "route", title_field])
	}


def _stakeholder_pages(lang, published_only=True):
	"""{(party_type, party): page} for Stakeholder Web Profiles (published ones by default), with the
	website section of their type. Anonymous pages (Publish As "Anonymous", or no approval to be named)
	get a neutral title; the URL (route) is neutral for every page. Only named pages may be linked from
	named content.

	``published_only=False`` also returns unpublished profiles (``page.published`` is then False): an
	anonymous stakeholder must not be named through its people even before its own page goes live."""
	industry_titles = _industry_titles(lang)
	section_of = {SECTIONS[s]["stakeholder_type"]: s for s in STAKEHOLDER_SECTIONS}
	pages = {}
	for r in attach_texts("Stakeholder Web Profile", frappe.get_all("Stakeholder Web Profile",
			filters={"published": 1} if published_only else None,
			fields=["name", "stakeholder_type", "party_type", "party", "party_name", "publish_as", "naming_approved",
				"industry", "region", "route", "published"])):
		if r.stakeholder_type not in section_of:
			continue
		named = r.publish_as == "Named" and bool(r.naming_approved)  # approval is checked on save too
		industry = industry_titles.get(r.industry) or _(r.industry) if r.industry else ""
		descriptor = ", ".join(filter(None, [_("{0} company").format(industry) if industry else _("Company"), r.region]))
		if not named:
			# Editors may write a better neutral title as the row title (e.g. "Mittelständischer Maschinenbauer").
			descriptor = localized(r, "title", lang, fallback=False) or descriptor
		pages[(r.party_type, r.party)] = frappe._dict(
			name=r.name,
			section=section_of[r.stakeholder_type],
			named=named,
			published=bool(r.published),
			slug=r.route,
			title=r.party_name if named else descriptor,
			descriptor=descriptor,
		)
	return pages


def _years_between(start, end=None):
	if not start:
		return None
	start, end = getdate(start), getdate(end) if end else date.today()
	return max(0, int((end - start).days // 365.25))


def _years_label(years):
	if years == 0:
		return _("Less than a year")
	return _("1 year") if years == 1 else _("{0} years").format(years)


# --- loaders --------------------------------------------------------------------------------------


def _team_memberships():
	"""{employee: [Team name]} for teams that have a published Team Web Profile."""
	teams = frappe.get_all("Team Web Profile", filters={"published": 1}, fields=["team", "team_lead"])
	members = {}
	for team in teams:
		employees = frappe.get_all("Team Members", filters={"parent": team.team, "parenttype": "Team"}, pluck="employee")
		for employee in dict.fromkeys([team.team_lead, *employees]):
			if employee:
				members.setdefault(employee, []).append(team.team)
	return members


PARTY_BADGES = {"Customer": "Customer", "Supplier": "Partner", "Sales Partner": "Partner"}


def load_people(lang):
	"""phamos employees (current + alumni) and consenting people from customers and partners."""
	records = attach_texts("Person Web Profile", frappe.get_all(
		"Person Web Profile",
		filters={"published": 1},
		fields=["name", "party_type", "party", "full_name", "status", "designation", "company_name", "department",
			"date_of_joining", "relieving_date", "publication_consent", "alumni_consent", "contact_consent",
			"email_id", "route", "image", "sort_order", "publish_as"],
	))
	departments = _profile_map("Department Web Profile", "department", "department_name")
	teams = _profile_map("Team Web Profile", "team", "team_name")
	modules = _profile_map("Module Web Profile", "name", "module_name")
	languages = dict(frappe.get_all("Language", fields=["name", "language_name"], as_list=True))
	person_modules = _children("Web Profile Module", "Person Web Profile", "module")
	person_languages = _children("Web Profile Language", "Person Web Profile", "language")
	memberships = _team_memberships()
	stakeholder_pages = _stakeholder_pages(lang, published_only=False)
	links = {}
	for row in frappe.get_all("Employee Profile-Social Media", filters={"parenttype": "Person Web Profile"},
			fields=["parent", "platform", "description", "profile_link"], order_by="idx asc"):
		url = normalize_url(row.profile_link)  # validated on save; checked again before it reaches an href
		if url:
			links.setdefault(row.parent, []).append(
				social_link(row.platform or detect_platform(url), url, row.description))

	items = []
	for r in records:
		employee = r.party_type == "Employee"
		if employee and r.status not in ("Active", "Left"):
			continue
		if not employee and not r.publication_consent:
			continue  # external people are only ever shown with their consent
		alumni = employee and r.status == "Left"
		# Same rule as PersonWebProfile.shown_named (phamos/phamos#1509).
		masked = r.publish_as == "Anonymous" or (alumni and not r.alumni_consent)
		designation = _(r.designation) if r.designation else ""
		# The organization of an external person. If its stakeholder page is anonymous, the person shows
		# that page's neutral title (and links to the page, whose URL is neutral anyway), so the
		# stakeholder is never named through its people.
		organization, organization_url = (r.company_name if not employee else None), None
		page = stakeholder_pages.get((r.party_type, r.party)) if not employee else None
		if page:
			organization = page.title if not page.named else organization
			organization_url = item_url(page.section, page.slug, lang) if page.published else None
		if masked:
			title = (_("Former colleague") if alumni else _("Team member")) if employee else \
				(_("Customer contact") if r.party_type == "Customer" else _("Partner contact"))
			item = _item("people", r, lang, title, r.route, subtitle=designation, masked=True)
		else:
			subtitle = designation if employee else " · ".join(filter(None, [designation, organization]))
			item = _item("people", r, lang, r.full_name, r.route, subtitle=subtitle, image=r.image)

		status = "alumni" if alumni else "current" if employee else "partners"
		_facet(item, "status", status, "")
		# Recommended order without a filter: our team, then customers and partners, then alumni.
		item["sort"]["manual"] = [{"current": 0, "partners": 1, "alumni": 2}[status], *item["sort"]["manual"]]
		if organization:
			_facet(item, "organization", slugify(organization), organization)
			item["chips"].append(organization)
			item["badge"] = _(PARTY_BADGES.get(r.party_type, "Partner"))
		dept = departments.get(r.department) if employee else None
		if dept:
			_facet(item, "department", dept[0], _(dept[1]))
			item["chips"].append(_(dept[1]))
		for team in memberships.get(r.party, []) if employee else []:
			if team in teams:
				_facet(item, "team", teams[team][0], teams[team][1])
		if r.designation:
			_facet(item, "designation", r.designation, designation)
		for module in person_modules.get(r.name, []):
			if module in modules:
				_facet(item, "module", modules[module][0], _(modules[module][1]))
		years = _years_between(r.date_of_joining, r.relieving_date if alumni else None) if employee else None
		if years is not None:
			item["numbers"]["tenure"] = years
			item["chips"].append(_years_label(years))
		for code in person_languages.get(r.name, []):
			_facet(item, "language", code, _(languages.get(code) or code))

		item["socials"] = [] if masked else links.get(r.name, [])  # anonymous alumni never show socials
		item["sort"]["tenure"] = -(years or 0)
		item["search"] = " ".join(filter(None, [None if masked else r.full_name, designation,
			organization])).lower()
		if alumni:
			item["badge"] = _("Alumni")
		if not masked:
			item["summary"] = localized(r, "summary", lang)
			item["body"] = localized(r, "content", lang)
		item["data"] = {
			"party_type": r.party_type,
			"party": r.party,
			"organization": organization,
			"organization_url": organization_url,
			"years": years,
			"alumni": alumni,
			# Only a flag reaches the page; the address stays on the server (see contact.py).
			# phamos people take requests through the CRM (Opportunity); external people need their
			# consent and a forwarding address. See contact.py.
			# Anonymous people are never contactable, not even through phamos (phamos/phamos#1509).
			"contactable": not masked and ((employee and not alumni) or bool(r.contact_consent and r.email_id)),
			"first_name": (r.full_name or "").split(" ")[0] if not masked else "",
			"start_year": getdate(r.date_of_joining).year if r.date_of_joining else None,
			"end_year": getdate(r.relieving_date).year if (alumni and r.relieving_date) else None,
		}
		items.append(item)
	return items


def load_departments(lang):
	people = get_items("people", lang)
	items = []
	for r in _published("Department Web Profile", ["department", "department_name", "lead"]):
		item = _item("departments", r, lang, _(r.department_name), r.route, image=r.image)
		members = [p for p in people if item["slug"] in p.facets.get("department", []) and p.facets["status"] == ["current"]]
		count = len(members)
		item["subtitle"] = localized(r, "summary", lang)
		item["chips"].append(_("{0} people").format(count) if count != 1 else _("1 person"))
		item["numbers"]["size"] = count
		item["sort"]["size"] = -count
		item["search"] = item["title"].lower()
		item["summary"] = localized(r, "summary", lang)
		item["body"] = localized(r, "content", lang)
		item["data"] = {"lead": r.lead, "count": count}
		items.append(item)
	return items


def load_teams(lang):
	people = get_items("people", lang)
	items = []
	for r in _published("Team Web Profile", ["team", "team_name", "team_lead", "founded"]):
		item = _item("teams", r, lang, r.team_name, r.route, image=r.image)
		members = [p for p in people if item["slug"] in p.facets.get("team", []) and p.facets["status"] == ["current"]]
		count = len(members)
		item["subtitle"] = localized(r, "summary", lang)
		item["chips"].append(_("{0} members").format(count) if count != 1 else _("1 member"))
		if r.founded:
			item["chips"].append(_("Founded {0}").format(r.founded))
			item["numbers"]["founded"] = r.founded
		item["numbers"]["size"] = count
		item["sort"]["size"] = -count
		item["search"] = item["title"].lower()
		item["summary"] = localized(r, "summary", lang)
		item["body"] = localized(r, "content", lang)
		item["data"] = {"lead": r.team_lead, "count": count, "founded": r.founded}
		items.append(item)
	return items


def load_modules(lang):
	industries = _profile_map("Industry Web Profile", "industry", "industry")
	industry_titles = _industry_titles(lang)
	module_industries = {}
	for industry, modules in _children("Web Profile Module", "Industry Web Profile", "module").items():
		for module in modules:
			module_industries.setdefault(module, []).append(industry)
	items = []
	for r in _published("Module Web Profile", ["module", "module_name", "icon", "complexity", "typical_duration", "key_person"]):
		item = _item("modules", r, lang, _(r.module_name), r.route, image=r.image)
		item["icon"] = module_icon(r.icon)
		item["subtitle"] = localized(r, "summary", lang)
		if r.complexity:
			_facet(item, "complexity", r.complexity, _(r.complexity))
			item["chips"].append(_(r.complexity))
		if r.typical_duration:
			item["chips"].append(r.typical_duration)
		for industry in module_industries.get(r.name, []):
			if industry in industries:
				label = industry_titles.get(industry) or _(industry)
				_facet(item, "industry", industries[industry][0], label)
		item["search"] = item["title"].lower()
		item["summary"] = localized(r, "summary", lang)
		item["body"] = localized(r, "content", lang)
		item["data"] = {"complexity": r.complexity, "duration": r.typical_duration, "key_person": r.key_person}
		items.append(item)
	return items


def load_implementations(lang):
	industries = _profile_map("Industry Web Profile", "industry", "industry")
	industry_titles = _industry_titles(lang)
	modules = _profile_map("Module Web Profile", "name", "module_name")
	teams = _profile_map("Team Web Profile", "team", "team_name")
	implementation_modules = _children("Web Profile Module", "Implementation Web Profile", "module")
	people = {p.name: p for p in get_items("people", lang)}
	customer_pages = {party: p for (party_type, party), p in _stakeholder_pages(lang).items()
		if party_type == "Customer" and p.section == "customers"}
	project_people = {}
	for row in frappe.get_all("Implementation Web Profile Person", filters={"parenttype": "Implementation Web Profile"},
			fields=["parent", "person", "role", "key_person"], order_by="idx asc"):
		project_people.setdefault(row.parent, []).append(row)
	items = []
	for r in _published("Implementation Web Profile", ["implementation", "customer", "implementation_status", "team",
			"start_date", "industry", "customer_approved", "region"]):
		if r.implementation_status == "Cancelled":
			continue
		industry_label = industry_titles.get(r.industry) or _(r.industry) if r.industry else ""
		year = getdate(r.start_date).year if r.start_date else None
		masked = not r.customer_approved
		descriptor = ", ".join(filter(None, [_("{0} company").format(industry_label) if industry_label else _("Company"), r.region]))
		title = localized(r, "title", lang) or (descriptor if masked else r.customer)
		if masked:
			item = _item("implementations", r, lang, title, r.route, subtitle="" if title == descriptor else descriptor,
				masked=True)
		else:
			item = _item("implementations", r, lang, title, r.route, subtitle=r.customer, image=r.image)
		if r.industry in industries:
			_facet(item, "industry", industries[r.industry][0], industry_label)
		for module in implementation_modules.get(r.name, []):
			if module in modules:
				_facet(item, "module", modules[module][0], _(modules[module][1]))
		if r.team in teams:
			_facet(item, "team", teams[r.team][0], teams[r.team][1])
			item["chips"].append(teams[r.team][1])
		if year:
			item["numbers"]["year"] = year
			item["chips"].append(str(year))
		item["sort"]["newest"] = -(year or 0)
		item["search"] = " ".join(filter(None, [title, item["subtitle"]])).lower()
		item["summary"] = localized(r, "summary", lang)
		item["body"] = localized(r, "content", lang)
		# Both sides of the project. Customer-side people only when the customer may be named:
		# their profile shows the organization, which would otherwise reveal an anonymous customer.
		on_project = []
		for row in project_people.get(r.name, []):
			person = people.get(row.person)
			if person and (person.data["party_type"] == "Employee" or not masked):
				on_project.append({"person": person.name, "role": _(row.role) if row.role else "", "key": bool(row.key_person)})
		item["data"] = {
			"people": on_project,
			"status": _("Completed") if r.implementation_status == "Completed" else _("Ongoing"),
			"year": year,
			"team": teams.get(r.team),
			"industry": (industries[r.industry][0], industry_label) if r.industry in industries else None,
			"customer": None if masked else r.customer,
			# Server-side only (never rendered): lets the customer page find its projects.
			"_customer": r.customer,
			# Named cases link to a named customer page, anonymous cases only to an anonymous one.
			"customer_link": {"value": customer_pages[r.customer].title, "url": item_url("customers", customer_pages[r.customer].slug, lang)}
				if r.customer in customer_pages and customer_pages[r.customer].named != masked else None,
		}
		items.append(item)
	return items


def load_industries(lang):
	modules = _profile_map("Module Web Profile", "name", "module_name")
	industry_modules = _children("Web Profile Module", "Industry Web Profile", "module")
	items = []
	for r in _published("Industry Web Profile", ["industry", "key_person"]):
		title = localized(r, "title", lang, fallback=False) or _(r.industry)
		item = _item("industries", r, lang, title, r.route, image=r.image)
		item["subtitle"] = localized(r, "summary", lang)
		for module in industry_modules.get(r.name, []):
			if module in modules:
				_facet(item, "module", modules[module][0], _(modules[module][1]))
		count = len(item["facets"].get("module", []))
		if count:
			item["chips"].append(_("{0} modules").format(count) if count != 1 else _("1 module"))
		item["search"] = title.lower()
		item["summary"] = localized(r, "summary", lang)
		item["body"] = localized(r, "content", lang)
		item["data"] = {"key_person": r.key_person}
		items.append(item)
	return items


def load_stakeholders(section, lang):
	"""Customer or partner pages (one Stakeholder Web Profile type per section). Named with approval;
	otherwise anonymous: neutral title and URL, no logo, website or their people, and only their
	anonymous implementations."""
	industries = _profile_map("Industry Web Profile", "industry", "industry")
	pages = _stakeholder_pages(lang)
	implementations = get_items("implementations", lang)
	people = get_items("people", lang)
	items = []
	for r in attach_texts("Stakeholder Web Profile", frappe.get_all("Stakeholder Web Profile",
			filters={"published": 1, "stakeholder_type": SECTIONS[section]["stakeholder_type"]},
			fields=["name", "route", "sort_order", "image", "party_type", "party", "party_name", "industry", "website",
				"region", "key_person", "account_manager"])):
		page = pages[(r.party_type, r.party)]
		masked = not page.named
		item = _item(section, r, lang, page.title, page.slug, image=r.image, masked=masked)
		# Named page: the customer's named projects. Anonymous page: only their anonymous projects.
		projects = [i for i in implementations
			if r.party_type == "Customer" and i.data.get("_customer") == r.party and i.masked == masked]
		years = [i.data["year"] for i in projects if i.data.get("year")]
		since = min(years) if years else None
		industry_label = next((i.labels["industry"][v] for i in projects for v in i.facets.get("industry", [])), None) \
			or (_(r.industry) if r.industry else "")
		if r.industry in industries:
			_facet(item, "industry", industries[r.industry][0], industry_label)
		for project in projects:
			for key in ("module", "team"):
				for value in project.facets.get(key, []):
					_facet(item, key, value, project.labels[key][value])
		if since:
			item["numbers"]["since"] = since
			item["chips"].append(_("Since {0}").format(since))
		if projects:
			item["chips"].append(_("{0} implementations").format(len(projects)) if len(projects) != 1 else _("1 implementation"))
		elif industry_label:
			item["chips"].append(industry_label)
		item["sort"]["newest"] = -(since or 0)
		item["search"] = " ".join(filter(None, [page.title, industry_label, r.region])).lower()
		item["summary"] = localized(r, "summary", lang)
		item["body"] = localized(r, "content", lang)
		item["data"] = {
			"customer": None if masked else r.party,
			"stakeholder_type": SECTIONS[section]["stakeholder_type"],
			"website": None if masked else r.website,
			"region": r.region, "since": since,
			"projects": [p.slug for p in projects],
			# Their people would reveal an anonymous stakeholder through their organization.
			"people": [] if masked else [p.slug for p in people
				if p.data.get("party_type") == r.party_type and p.data.get("party") == r.party],
			"key_person": None if masked else r.key_person,
			"account_manager": r.account_manager,
			"industry": (industries[r.industry][0], industry_label) if r.industry in industries else None,
		}
		items.append(item)
	return items


LOADERS = {
	"people": load_people,
	"departments": load_departments,
	"teams": load_teams,
	"modules": load_modules,
	"implementations": load_implementations,
	"industries": load_industries,
	"customers": lambda lang: load_stakeholders("customers", lang),
	"partners": lambda lang: load_stakeholders("partners", lang),
}


# --- profile pages --------------------------------------------------------------------------------


def related(section, lang, *, facet=None, values=None, slugs=None, exclude=None, current_only=False):
	"""Items of ``section`` linked to a profile, plus the filtered-list URL behind "See all"."""
	from phamos.web_profile.utils import build_query

	items = get_items(section, lang)
	if slugs is not None:
		matches = [i for i in items if i.slug in slugs]
		see_all = None
	else:
		values = [v for v in (values or []) if v]
		matches = [i for i in items if set(i.facets.get(facet, [])) & set(values)]
		see_all = section_url(section, lang) + build_query({facet: values}) if values else None
	if current_only and section == "people":
		matches = [i for i in matches if i.facets.get("status") == ["current"]]
	if exclude:
		matches = [i for i in matches if i.slug != exclude]
	return matches, see_all


def contact_dialog(target, lang, label=None):
	"""Button + dialog texts for the shared contact workflow (phamos.web_profile.contact.submit).
	The server decides the actual workflow again from section + slug; these texts only explain it."""
	person = target if target.section == "people" and target.data.get("contactable") else None
	external = bool(person and person.data["party_type"] != "Employee")
	name = person.data["first_name"] if person else None
	if external:
		intro = _("Your request is forwarded to {0} by email, who replies to you directly. Their address stays private.").format(name)
		consent = _("I agree that phamos forwards my name, contact details and message to {0}.").format(person.title)
	elif person:
		intro = _("{0} receives your request at phamos and gets back to you.").format(name)
		consent = _("I agree that phamos stores my name, contact details and message to answer my request.")
	else:
		intro = _("Tell us what you need. The right person at phamos gets back to you.")
		consent = _("I agree that phamos stores my name, contact details and message to answer my request.")
	return {
		"label": label or _("Contact {0}").format(name),
		"title": _("Contact {0}").format(name) if person else (label or _("Contact phamos")),
		"intro": intro,
		"consent": consent,
		"section": target.section,
		"slug": target.slug,
		"dialog": True,
	}


def _person_by_employee(employee, lang):
	for person in get_items("people", lang):
		if employee and person.data.get("party_type") == "Employee" and person.data.get("party") == employee:
			return person
	return None


def _person_by_name(name, lang):
	for person in get_items("people", lang):
		if name and person.name == name:
			return person
	return None


def key_people(item, lang):
	"""The person (or people) a detail page is about, for the sticky sidebar: the person itself,
	a team or department lead, an implementation's managers on both sides, a topic's contact."""
	section, cards = item.section, []

	def add(person, role):
		if person and all(c["person"].name != person.name for c in cards):
			cards.append({"person": person, "role": role,
				"contact": contact_dialog(person, lang) if person.data.get("contactable") else None})

	if section == "people":
		add(item, item.subtitle)
	elif section == "departments":
		add(_person_by_employee(item.data.get("lead"), lang), _("Head of department"))
	elif section == "teams":
		add(_person_by_employee(item.data.get("lead"), lang), _("Team lead"))
	elif section == "implementations":
		people = {p.name: p for p in get_items("people", lang)}
		entries = [dict(e, person=people[e["person"]]) for e in item.data.get("people", [])]
		for side in ("phamos", "customer"):
			mine = [e for e in entries if (e["person"].data["party_type"] == "Employee") == (side == "phamos")]
			chosen = [e for e in mine if e["key"]] or mine[:1]
			for e in chosen[:1]:
				org = "phamos" if side == "phamos" else e["person"].data.get("organization")
				add(e["person"], " · ".join(filter(None, [e["role"], org])))
	elif section in STAKEHOLDER_SECTIONS:
		contact = _person_by_name(item.data.get("key_person"), lang) or next(
			(p for p in get_items("people", lang) if p.slug in item.data.get("people", [])), None)
		add(contact, " · ".join(filter(None, [_("Key contact"), item.title])))
		add(_person_by_employee(item.data.get("account_manager"), lang), _("Account manager · phamos"))
	else:  # modules, industries
		add(_person_by_name(item.data.get("key_person"), lang), _("Your contact"))

	if not cards:
		# No single person on this page: show the sales contact (Web Profile Settings).
		settings = frappe.db.get_singles_dict("Web Profile Settings")
		add(_person_by_name(settings.get("sales_contact"), lang),
			_(settings.get("sales_contact_role") or "Sales · phamos"))
	return cards


def _person_link(employee, lang):
	"""Fact value for a lead: the person's tile title + URL (already anonymised when needed)."""
	for person in get_items("people", lang):
		if person.data.get("party_type") == "Employee" and person.data.get("party") == employee:
			return {"value": person.title, "url": person.url}
	return None


def _join(values):
	"""'A', 'A and B', 'A, B and C' in the request language."""
	values = [v for v in values if v]
	if len(values) < 2:
		return "".join(values)
	return _("{0} and {1}").format(", ".join(values[:-1]), values[-1])


def _labels(item, key):
	return [item.labels.get(key, {}).get(v, v) for v in item.facets.get(key, [])]


def build_profile(item, lang):
	"""Stats, overview text, related sections (each with an introduction), CTA and schema.org type.

	Same skeleton for every section. The overview is written from the record's own facts so every
	page has substantial, crawlable text even before an editor adds a description; anonymous
	records never get identifying details in it.
	"""
	section, facts, sections, cta = item.section, [], [], None
	first = _("this former colleague") if item.masked and section == "people" else (item.data.get("first_name") or item.title)

	def add_related(title, intro, section_key, **kwargs):
		matches, see_all = related(section_key, lang, **kwargs)
		if matches:
			sections.append({"title": title, "intro": intro, "tiles": matches[:6], "count": len(matches),
				"see_all": see_all if len(matches) > 6 or see_all else None})

	def facet_links(key, target_section):
		labels = item.labels.get(key, {})
		return [{"value": labels[v], "url": item_url(target_section, v, lang)} for v in item.facets.get(key, [])]

	if section == "people":
		employee = item.data["party_type"] == "Employee"
		if item.data.get("organization") and not employee:
			url = item.data.get("organization_url")
			facts.append({"label": _("Organization"), "value": item.data["organization"],
				"links": [{"value": item.data["organization"], "url": url}] if url else None})
		facts += [{"label": _("Department"), "links": facet_links("department", "departments")}]
		facts += [{"label": _("Team"), "links": facet_links("team", "teams")}]
		if item.data.get("years") is not None:
			span = f" ({item.data['start_year']}–{item.data['end_year']})" if item.data.get("end_year") and not item.masked else ""
			facts.append({"label": _("Time at phamos"), "value": _years_label(item.data["years"]) + span})
		langs = [{"label": item.labels["language"][v], "flag": flag_url(v)} for v in item.facets.get("language", [])]
		if langs:
			facts.append({"label": _("Languages"), "value": ", ".join(lang_["label"] for lang_ in langs), "flags": langs})

		designation, modules = _join(_labels(item, "designation")), _join(_labels(item, "module"))
		if item.masked:
			overview = [_("A former colleague who worked at phamos as {0} for {1}.").format(designation, _years_label(item.data["years"] or 0))]
		elif employee:
			overview = [_("{0} works at phamos as {1}.").format(item.title, designation) if not item.data.get("alumni")
				else _("{0} worked at phamos as {1} for {2}.").format(item.title, designation, _years_label(item.data["years"] or 0))]
		else:
			overview = [_("{0} is {1} at {2} and works with phamos on eye level.").format(item.title, designation, item.data.get("organization"))]

		add_related(_("Module expertise"), _("The ERPNext modules {0} knows well. Each module page explains what the module covers and who else at phamos works with it.").format(first),
			"modules", slugs=item.facets.get("module", []))
		projects = [i.slug for i in get_items("implementations", lang)
			if any(p["person"] == item.name for p in i.data.get("people", []))]
		add_related(_("Implementations"), _("Projects {0} has worked on, with the industry, team and modules of each.").format(first),
			"implementations", slugs=projects)
		if employee and not item.data.get("alumni"):
			add_related(_("Teammates"), _("The people {0} works with every day in the same team.").format(first),
				"people", facet="team", values=item.facets.get("team"), exclude=item.slug, current_only=True)
		# Own contact button when contactable; none at all on anonymous profiles.
		cta = None if item.data.get("contactable") or item.masked else contact_dialog(item, lang, _("Start a conversation"))
		employer = ORGANIZATION if employee else {"@type": "Organization", "name": item.data.get("organization")}
		schema = None if item.masked else {"@type": "Person", "name": item.title, "jobTitle": designation or None,
			"worksFor" if not item.data.get("alumni") else "alumniOf": employer}

	elif section == "departments":
		lead = _person_link(item.data.get("lead"), lang)
		overview = [_("The {0} department at phamos has {1} and is led by {2}.").format(
			item.title, _("{0} people").format(item.data["count"]) if item.data["count"] != 1 else _("1 person"),
			lead["value"] if lead else _("its department head"))]
		add_related(_("People in this department"), _("Everyone currently working in {0}. Open a profile to see their expertise, team and projects.").format(item.title),
			"people", facet="department", values=[item.slug], current_only=True)
		cta = {"label": _("View open roles"), "url": "/jobs"}
		schema = {"@type": "Organization", "name": item.title, "parentOrganization": ORGANIZATION}

	elif section == "teams":
		lead = _person_link(item.data.get("lead"), lang)
		if item.data.get("founded"):
			facts.append({"label": _("Founded"), "value": str(item.data["founded"])})
		overview = [_("{0} is a delivery team at phamos with {1}.").format(item.title,
			_("{0} members").format(item.data["count"]) if item.data["count"] != 1 else _("1 member"))]
		if lead:
			overview.append(_("The team is led by {0}.").format(lead["value"]))
		add_related(_("Members"), _("The people in {0}. Together they take an implementation from the first workshop to go-live.").format(item.title),
			"people", facet="team", values=[item.slug], current_only=True)
		add_related(_("Implementations"), _("Projects delivered by {0}, with the industry and modules of each.").format(item.title),
			"implementations", facet="team", values=[item.slug])
		cta = contact_dialog(item, lang, _("Start a conversation"))
		schema = {"@type": "Organization", "name": item.title, "parentOrganization": ORGANIZATION}

	elif section == "modules":
		if item.data.get("complexity"):
			facts.append({"label": _("Complexity"), "value": _(item.data["complexity"])})
		if item.data.get("duration"):
			facts.append({"label": _("Typical duration"), "value": item.data["duration"]})
		overview = [_("{0} is an ERPNext module that phamos introduces step by step, together with the people who will use it.").format(item.title)]
		# Content first (projects, industries), the people afterwards; the sidebar keeps the key person.
		add_related(_("Implementations"), _("Projects in which {0} was introduced.").format(item.title),
			"implementations", facet="module", values=[item.slug])
		add_related(_("Industries"), _("Industries where {0} plays a central role.").format(item.title),
			"industries", facet="module", values=[item.slug])
		add_related(_("Experts"), _("phamos people with hands-on experience in {0}.").format(item.title),
			"people", facet="module", values=[item.slug], current_only=True)
		cta = contact_dialog(item, lang, _("Talk to us about this module"))
		schema = {"@type": "Service", "name": item.title, "serviceType": "ERPNext implementation", "provider": ORGANIZATION}

	elif section == "implementations":
		if item.data.get("customer_link"):
			facts.append({"label": _("Customer"), "links": [item.data["customer_link"]]})
		facts.append({"label": _("Industry"), "links": facet_links("industry", "industries")})
		facts.append({"label": _("Team"), "links": facet_links("team", "teams")})
		if item.data.get("year"):
			facts.append({"label": _("Started"), "value": str(item.data["year"])})
		facts.append({"label": _("Status"), "value": item.data["status"]})
		if item.masked:
			overview = [_("An ERPNext implementation for a customer who is not named here.")]
		else:
			overview = [_("An ERPNext implementation for {0}.").format(item.data.get("customer"))]
		people = {p.name: p for p in get_items("people", lang)}
		on_project = []
		for entry in item.data.get("people", []):
			person = people[entry["person"]]
			org = person.data.get("organization") if person.data["party_type"] != "Employee" else "phamos"
			on_project.append(frappe._dict({**person, "subtitle": " · ".join(filter(None, [entry["role"], org]))}))
		# Content first (modules, similar projects), the people afterwards; the sidebar keeps the key people.
		add_related(_("Modules in this project"), _("The ERPNext modules introduced in this project."),
			"modules", slugs=item.facets.get("module", []))
		add_related(_("Similar implementations"), _("Other projects in the same industry."),
			"implementations", facet="industry", values=item.facets.get("industry"), exclude=item.slug)
		if on_project:
			sections.append({"title": _("People on this project"), "count": len(on_project), "see_all": None, "tiles": on_project,
				"intro": _("The phamos people who worked on this project. The customer is not named, so the customer's team is not shown either.") if item.masked
					else _("The people who shaped this project, from phamos and from the customer's side, working together on eye level.")})
		cta = contact_dialog(item, lang, _("Talk to us about your project"))
		schema = {"@type": "CreativeWork", "name": item.title, "genre": "Case study", "author": ORGANIZATION}
		if item.data.get("customer"):
			schema["about"] = {"@type": "Organization", "name": item.data["customer"]}

	elif section in STAKEHOLDER_SECTIONS:
		partner = section == "partners"
		if item.data.get("industry"):
			facts.append({"label": _("Industry"), "links": facet_links("industry", "industries")})
		if item.data.get("region") and not item.masked:  # an anonymous title already names the region
			facts.append({"label": _("Region"), "value": item.data["region"]})
		if item.data.get("since"):
			facts.append({"label": _("Customer since"), "value": str(item.data["since"])})
		modules = _labels(item, "module")
		if modules:
			facts.append({"label": _("Modules"), "links": facet_links("module", "modules")})
		if item.data.get("website"):
			site = item.data["website"] if "://" in item.data["website"] else "https://" + item.data["website"]
			facts.append({"label": _("Website"), "links": [{"value": item.data["website"].split("://")[-1].rstrip("/"), "url": site, "external": True}]})
		industry = item.data["industry"][1] if item.data.get("industry") else None
		if item.masked:
			overview = [_("A phamos partner that is not named here.") if partner
				else _("A phamos customer that is not named here. Its projects are shown without identifying details.")]
		else:
			overview = [(_("{0} is a phamos partner{1}.") if partner else _("{0} is a phamos customer{1}.")).format(
				item.title, _(" in {0}").format(industry) if industry else "")]
		add_related(_("People at {0}").format(item.title), _("The people at {0} who work with phamos, on eye level.").format(item.title),
			"people", slugs=item.data.get("people", []))
		add_related(_("Implementations"), _("Projects phamos delivered for this customer.") if item.masked
			else _("Projects phamos delivered for {0}.").format(item.title), "implementations", slugs=item.data["projects"])
		if item.data.get("industry"):
			add_related((_("More partners in {0}") if partner else _("More customers in {0}")).format(industry),
				_("Other companies in the same industry that work with phamos."),
				section, facet="industry", values=[item.data["industry"][0]], exclude=item.slug)
		cta = contact_dialog(item, lang, _("Talk to us about a partnership") if partner else _("Talk to us about your project"))
		schema = None if item.masked else {"@type": "Organization", "name": item.title, "url": item.data.get("website") or None}

	else:  # industries
		overview = [_("phamos introduces ERPNext for companies in {0}.").format(item.title)]
		add_related(_("Relevant modules"), _("The ERPNext modules that matter most in {0}.").format(item.title),
			"modules", slugs=item.facets.get("module", []))
		add_related(_("Implementations"), _("Projects we delivered in {0}.").format(item.title),
			"implementations", facet="industry", values=[item.slug])
		add_related(_("Customers"), _("Companies in {0} that work with phamos and agreed to be named.").format(item.title),
			"customers", facet="industry", values=[item.slug])
		cta = contact_dialog(item, lang, _("Talk to us about your industry"))
		schema = {"@type": "Thing", "name": item.title}

	facts = [f for f in facts if f.get("value") or f.get("links")]
	return _dedupe(item, {"facts": facts, "overview": " ".join(overview), "related": sections, "cta": cta,
		"schema": schema, "key_people": key_people(item, lang)})


def _dedupe(item, profile):
	"""Show each piece of information once per page (phamos/phamos#1492 design rules).

	- Key people in the sidebar are not repeated in the card sections; empty sections disappear.
	- Cards don't repeat the page they are on (no "Nordwerk" chip on Nordwerk's page).
	- The generated overview is a fallback for pages without editor text.
	- One contact action per person: no generic "Talk to us" next to a contact button.
	- The header subtitle is dropped when the sidebar shows the same facts as cards/chips.
	"""
	key_names = {card["person"].name for card in profile["key_people"]}
	own = {item.title}

	def clean(tile):
		chips = [c for c in tile.chips if c not in own]
		subtitle = " · ".join(p for p in (tile.subtitle or "").split(" · ") if p not in own)
		return frappe._dict({**tile, "chips": chips, "subtitle": "" if subtitle == tile.title else subtitle})

	sections = []
	for block in profile["related"]:
		tiles = [clean(t) for t in block["tiles"] if not (t.section == "people" and t.name in key_names)]
		if tiles:
			removed = len(block["tiles"]) - len(tiles)
			sections.append({**block, "tiles": tiles, "count": block["count"] - removed})
	profile["related"] = sections

	if item.body:
		profile["overview"] = ""
	if any(card.get("contact") for card in profile["key_people"]) and (profile["cta"] or {}).get("dialog"):
		profile["cta"] = None
	profile["show_subtitle"] = not (item.section in STAKEHOLDER_SECTIONS or (item.section == "implementations" and item.data.get("customer_link")))
	return profile
