"""Go-live of one website section, by data only (phamos/phamos#1492, step 5).

A section goes live with Frappe's own tools, not with redirects in code:
- a *Website Route Redirect* row (Website Settings) for every old URL of the section,
- its old Web Pages unpublished (kept, so a rollback can bring them back).

Each section has a plan in `phamos.web_profile.golive_plans.<section>` with a `plan()` function that
returns the redirects and the pages to unpublish. Targets are worked out on the site that runs the
plan, because the new URLs are created there (person URLs are random codes, phamos/phamos#1512).

    bench --site <site> execute phamos.web_profile.golive.run --kwargs '{"section": "people"}'
    bench --site <site> execute phamos.web_profile.golive.run --kwargs '{"section": "people", "dry_run": 0}'
    bench --site <site> execute phamos.web_profile.golive.rollback --kwargs '{"section": "people", "dry_run": 0}'

`run` is a dry run unless `dry_run` is 0, and running it twice changes nothing. `rollback` removes
exactly the plan's redirect rows and republishes the pages that `run` unpublished.

Privacy: an old URL only leads to a profile that shows a name. Old URLs of anonymous people,
customers or cases lead to the section overview, so an old named URL never points at an anonymous
page (phamos/phamos#1487).
"""

import importlib
import re

import frappe
from frappe.website.utils import clear_cache

from phamos.web_profile.sections import get_items, section_url
from phamos.web_profile.utils import slugify

DEFAULT_LANGUAGE = "de"  # old URLs without a language go to the German page (x-default)
SECTION_KEY = re.compile(r"^[a-z_]+$")
MARK = "Unpublished by the website go-live of section '{0}' (phamos.web_profile.golive)."


# --- run / rollback --------------------------------------------------------------------------------


def run(section, dry_run=1, verbose=1):
	"""Create the section's redirects and unpublish its old Web Pages (dry run by default)."""
	plan = get_plan(section)
	settings = frappe.get_single("Website Settings")
	existing = {_path(row.source): row for row in settings.route_redirects}
	report = frappe._dict(added=[], unchanged=[], conflicts=[], unpublished=[], notes=plan.notes)

	for source, target in plan.redirects:
		row = existing.get(source)
		if not row:
			report.added.append((source, target))
			if not frappe.utils.cint(dry_run):
				settings.append("route_redirects", {"source": _pattern(source), "target": target,
					"redirect_http_status": "301"})
		elif row.target == target:
			report.unchanged.append((source, target))
		else:
			# Someone set this old URL up differently: leave it to a person to decide.
			report.conflicts.append((source, row.target, target))

	for name in plan.unpublish:
		if frappe.db.get_value("Web Page", name, "published"):
			report.unpublished.append(frappe.db.get_value("Web Page", name, "route"))
			if not frappe.utils.cint(dry_run):
				frappe.db.set_value("Web Page", name, "published", 0)
				# The mark tells the rollback which pages this run unpublished (and no others).
				frappe.get_doc("Web Page", name).add_comment("Info", MARK.format(section))

	if not frappe.utils.cint(dry_run):
		settings.save(ignore_permissions=True)
		_clear_caches()
	return _print(section, report, dry_run, verbose=verbose)


def rollback(section, dry_run=1, verbose=1):
	"""Undo `run`: remove exactly the plan's redirect rows and republish the Web Pages that `run`
	unpublished (marked with a comment); pages that were unpublished before stay unpublished."""
	plan = get_plan(section)
	planned = dict(plan.redirects)
	settings = frappe.get_single("Website Settings")
	keep, removed = [], []
	for row in settings.route_redirects:
		source = _path(row.source)
		(removed if planned.get(source) == row.target else keep).append(row)
	marks = frappe.get_all("Comment", filters={"reference_doctype": "Web Page", "comment_type": "Info",
		"content": MARK.format(section)}, fields=["name", "reference_name"])
	republished = [frappe.db.get_value("Web Page", m.reference_name, "route") for m in marks]

	if not frappe.utils.cint(dry_run):
		settings.set("route_redirects", keep)
		settings.save(ignore_permissions=True)
		for mark in marks:
			frappe.db.set_value("Web Page", mark.reference_name, "published", 1)
			frappe.delete_doc("Comment", mark.name, ignore_permissions=True)
		_clear_caches()
	report = frappe._dict(removed=[(_path(r.source), r.target) for r in removed], republished=republished)
	return _print(section, report, dry_run, title="rollback", verbose=verbose)


def get_plan(section):
	"""The plan of a section: {redirects: [(old path, new URL)], unpublish: [Web Page], notes: [...]}."""
	if not SECTION_KEY.match(section or ""):
		frappe.throw(f"Unknown section {section!r}")
	name = f"phamos.web_profile.golive_plans.{section}"
	try:
		module = importlib.import_module(name)
	except ModuleNotFoundError as error:
		if error.name != name:
			raise  # an import inside the plan is broken: show that, not "no plan"
		frappe.throw(f"No go-live plan for section {section!r} (phamos/web_profile/golive_plans/{section}.py)")
	plan = frappe._dict({"redirects": [], "unpublish": [], "notes": [], **module.plan()})
	# One target per old URL, never a redirect onto itself.
	seen, redirects = set(), []
	for source, target in plan.redirects:
		source = _path(source)
		if source and source not in seen and _path(target) != source:
			seen.add(source)
			redirects.append((source, target))
	plan.redirects = redirects
	return plan


# --- helpers for the section plans -----------------------------------------------------------------


def section_plan(section, old_prefixes, aliases=None, extra_sources=()):
	"""The usual plan of a profile section.

	- each old overview (`people`, `modules`, …) → the new overview (German);
	- each old Web Page below it (`modules/accounting`) → the profile with the same name, else the
	  new overview; the old pages are unpublished;
	- `aliases` maps an old slug to a profile slug when the names differ (`{"it": "software-development"}`);
	- `extra_sources` are old URLs without a Web Page (e.g. links that were broken before).
	"""
	listing = section_url(section, DEFAULT_LANGUAGE)
	index = named_profiles(section)
	aliases = aliases or {}
	redirects, unpublish, notes = [], [], []

	def target_for(slug, title=None):
		for key in (aliases.get(slug), slug, slugify(title or "")):
			if key and key in index:
				return index[key]
		return listing

	for prefix in old_prefixes:
		redirects.append((prefix, listing))
		for page in legacy_pages(prefix):
			slug = page.route[len(prefix):].strip("/")
			target = target_for(slug, page.title) if slug else listing
			redirects.append((page.route, target))
			unpublish.append(page.name)
			if slug and target == listing:
				notes.append(f"{page.route}: no named profile found, goes to the overview")
		for source in extra_sources:
			slug = source.strip("/").split("/")[-1]
			redirects.append((source, target_for(slug)))
	return {"redirects": redirects, "unpublish": unpublish, "notes": notes}


def named_profiles(section):
	"""{slug of a German or English title: German URL} of the published profiles that show a name.
	Anonymous profiles are left out on purpose: an old named URL must not lead to them."""
	index = {}
	for lang in (DEFAULT_LANGUAGE, "en"):
		for item in get_items(section, lang):
			if item.masked:
				continue
			url = section_url(section, DEFAULT_LANGUAGE) + "/" + item.slug
			for key in (slugify(item.title), slugify(item.name or "")):
				if key:
					index.setdefault(key, url)
	return index


def legacy_pages(prefix):
	"""The old Web Pages of a section: the overview `prefix` and everything below it."""
	pages = frappe.get_all("Web Page", fields=["name", "route", "title"], order_by="route asc")
	return [p for p in pages if (p.route or "").strip("/") == prefix or (p.route or "").strip("/").startswith(prefix + "/")]


def route_exists(path):
	"""A published Web Page already answers this path, so a redirect there would hide it."""
	return bool(frappe.db.exists("Web Page", {"route": path.strip("/"), "published": 1}))


# --- internals --------------------------------------------------------------------------------------


def _path(value):
	"""'/people/' → 'people'; a stored pattern 'people\\/a\\-b' → 'people/a-b'."""
	return re.sub(r"\\(.)", r"\1", (value or "").strip().strip("/").rstrip("$"))


def _pattern(path):
	# Frappe matches `source` as a regular expression: escape old URLs so they match literally.
	return re.escape(path)


def _clear_caches():
	frappe.cache.delete_key("website_redirects")
	clear_cache()


def _print(section, report, dry_run, title="run", verbose=1):
	mode = "DRY RUN, nothing changed" if frappe.utils.cint(dry_run) else "done"
	lines = [f"Go-live {title} '{section}' ({mode})"]
	for key, rows in report.items():
		if rows:
			lines.append(f"  {key} ({len(rows)}):")
			lines += [f"    {' → '.join(map(str, row)) if isinstance(row, tuple) else row}" for row in rows]
	if frappe.utils.cint(verbose):
		print("\n".join(lines))
	return report
