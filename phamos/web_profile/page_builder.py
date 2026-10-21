"""One-time conversion of the content Web Pages to content the Desk can edit (phamos/phamos#1539).

The `de/…` / `en/…` content pages were stored as content type *HTML*: the rendered output of Frappe's
Page Builder and Rich Text editor, copied from the old site. That can only be edited by someone who
reads HTML. This turns each page back into what it was made from:

- Legal pages (Impressum, Datenschutz, AGB, …) become *Rich Text*: one long text, owned by one person.
- All other pages become *Page Builder* blocks. A section rendered from one of Frappe's standard Web
  Templates (Hero, Section with Cards, …) gets that template again, with its values read back from the
  HTML; a contact button becomes a "phamos Contact Button" block; anything else becomes a "Markdown"
  block. Layout the templates do not know (rows and columns) is simplified to plain text; the report
  says where.

Only pages that are still *HTML* are touched, so running it again never overwrites edits made in the
Desk. The old HTML stays in the page (`main_section_html`, hidden by the content type): rollback only
switches the content type back. Every save is a Version of the page (Web Page tracks changes).

    bench --site <site> execute phamos.web_profile.page_builder.convert                       # dry run
    bench --site <site> execute phamos.web_profile.page_builder.convert --kwargs '{"dry_run": 0}'
    bench --site <site> execute phamos.web_profile.page_builder.rollback --kwargs '{"dry_run": 0}'

`pages` (a list of Web Page names) limits either to some pages.
"""

import re

import frappe
from bs4 import BeautifulSoup, NavigableString, Tag
from markdownify import markdownify

from phamos.web_profile.i18n import LANGUAGES

# Last route segment of the legal pages in every language.
LEGAL_SLUGS = {"impressum", "imprint", "datenschutz", "privacy", "agb", "terms"}
CONTACT_TEMPLATE = "phamos Contact Button"
# Tags a Markdown block can hold without losing anything.
SIMPLE_TAGS = {"p", "br", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "a", "strong", "b", "em", "i",
	"u", "span", "blockquote", "img", "table", "thead", "tbody", "tr", "th", "td", "hr", "code", "pre"}


def convert(dry_run=1, pages=None, verbose=1):
	report = []
	for page in _candidates(pages, content_type="HTML"):
		result = plan_page(page)
		report.append((page.name, result))
		if not int(dry_run):
			doc = frappe.get_doc("Web Page", page.name)
			doc.content_type = result.content_type
			if result.content_type == "Rich Text":
				doc.main_section = result.main_section
			else:
				doc.set("page_blocks", result.blocks)
			doc.save(ignore_permissions=True)
	if int(verbose):
		_print(report, dry_run)
	return report


def rollback(dry_run=1, pages=None, verbose=1):
	"""Show the old HTML again. Edits made since stay stored in the blocks / Rich Text, unseen."""
	names = [p.name for p in _candidates(pages, content_type=["in", ["Page Builder", "Rich Text"]]) if p.main_section_html]
	if not int(dry_run):
		for name in names:
			doc = frappe.get_doc("Web Page", name)
			doc.content_type = "HTML"
			doc.save(ignore_permissions=True)
	if int(verbose):
		print(f"page_builder rollback ({'dry run' if int(dry_run) else 'done'}): {len(names)} pages back to HTML")
		for name in names:
			print(f"  {name}")
	return names


def _candidates(pages, content_type):
	filters = {"content_type": content_type, "language": ["in", list(LANGUAGES)]}
	if pages:
		filters["name"] = ["in", frappe.parse_json(pages) if isinstance(pages, str) else pages]
	return frappe.get_all("Web Page", filters=filters, fields=["name", "route", "main_section_html"], order_by="route")


def plan_page(page):
	"""frappe._dict(content_type, blocks | main_section, notes) for one Web Page (name, route, HTML)."""
	soup = BeautifulSoup(page.main_section_html or "", "html.parser")
	for footer in soup.select("div.page-footer"):
		footer.decompose()
	for ui in soup.select("span.ql-ui"):  # Quill's list markers, added when it renders
		ui.decompose()
	if (page.route or "").strip("/").split("/")[-1] in LEGAL_SLUGS:
		return frappe._dict(content_type="Rich Text", main_section=_rich_text(soup), notes=[])
	blocks, notes = [], []
	for element in _sections(soup):
		blocks.append(_block(element, notes))
	return frappe._dict(content_type="Page Builder", blocks=[b for b in blocks if b], notes=notes)


# --- Rich Text ----------------------------------------------------------------------------------------


def _rich_text(soup):
	editor = soup.select_one(".ql-editor")
	if editor:  # the page was Rich Text before: its text exactly as the editor stored it
		return editor.decode_contents().strip()
	parts = []
	for element in _sections(soup):
		body = _body(element)
		collapsible = body.select_one(".section-with-collapsible-content")
		if collapsible:
			parts += [f"<h2>{_text(t)}</h2>" for t in collapsible.select(".section-title")]
			parts += [f"<p>{_text(t)}</p>" for t in collapsible.select(".section-description")]
			for item in collapsible.select(".collapsible-item"):
				parts.append(f"<h3>{_text(item.select_one('.collapsible-item-title'))}</h3>")
				content = item.select_one(".collapsible-content > div") or item.select_one(".collapsible-content")
				parts.append(content.decode_contents().strip() if content else "")
		else:
			parts.append(body.decode_contents().strip())
	return "\n".join(p for p in parts if p)


# --- Page Builder --------------------------------------------------------------------------------------


def _sections(soup):
	"""Top-level parts of the page; wrappers that only hold sections are opened."""
	for child in soup.children:
		if isinstance(child, NavigableString):
			if child.strip():
				wrapper = soup.new_tag("p")
				wrapper.string = child.strip()
				yield wrapper
			continue
		if not isinstance(child, Tag):
			continue
		if child.name != "section" and child.find("section"):
			yield from _sections(child)
		elif _text(child) or child.find("img"):
			yield child


def _body(element):
	return element.find("div", class_="container", recursive=False) or element


def _block(element, notes):
	template = element.get("data-section-template") if element.name == "section" else None
	body = _body(element)
	parser = PARSERS.get(template)
	if parser:
		values = parser(body, notes)
	elif body.find(attrs={"data-wp-contact-open": True}):
		template, values = CONTACT_TEMPLATE, _contact(body)
	else:
		if template:
			notes.append(f"section template {template!r} not known: kept as a Markdown block")
		template, values = "Markdown", {"content": _markdown(body, notes)}
	classes = (element.get("class") or []) if element.name == "section" else []
	return {
		"web_template": template,
		"web_template_values": frappe.as_json(values, indent=None),
		"add_container": 1 if body is not element or element.name != "section" else 0,
		"add_top_padding": int("section-padding-top" in classes),
		"add_bottom_padding": int("section-padding-bottom" in classes),
		"add_shade": int("bg-light" in classes),
		"add_border_at_top": int("border-top" in classes),
		"add_border_at_bottom": int("border-bottom" in classes),
		"section_id": element.get("id") if element.name == "section" else None,
	}


def _hero(body, notes):
	hero = body.select_one(".hero") or body
	title = hero.select_one(".hero-title")
	values = {"title": _text(title), "subtitle": _subtitle(hero, notes)}
	values.update(_buttons(hero.select(".hero-buttons a")))
	centered = "align-center" in (hero.get("class") or []) or (title and title.find("center"))
	values["align"] = "Center" if centered else "Left"
	return values


def _hero_with_right_image(body, notes):
	hero = body.select_one(".hero-with-right-image") or body
	image = hero.select_one("img.hero-image")
	values = {"title": _text(hero.select_one(".hero-title")), "subtitle": _subtitle(hero, notes),
		"image": _src(image), "contain_image": int(bool(image and "contain-image" in (image.get("class") or [])))}
	values.update(_buttons(hero.select(".hero-content a.btn")))
	return values


def _cards(body, notes):
	section = body.select_one(".section-with-cards") or body
	values = _heading(section)
	cards = section.select(".card")
	sizes = {"card-sm": "Small", "card-md": "Medium", "card-lg": "Large"}
	values["card_size"] = next((sizes[c] for c in (cards[0].get("class") if cards else []) if c in sizes), "Small")
	if len(cards) > 9:
		notes.append(f"{len(cards)} cards, the template holds 9: the rest was left out")
	for index, card in enumerate(cards[:9], start=1):
		link = card.select_one("a.stretched-link")
		url = link.get("href") if link else ""
		values.update({
			f"card_{index}_title": _text(card.select_one(".card-title")),
			f"card_{index}_content": _text(card.select_one(".card-text")),
			f"card_{index}_url": "" if url == "#" else url,
			f"card_{index}_image": _src(card.select_one("img.card-img-top")),
		})
	return values


def _features(body, notes):
	section = body.select_one(".section-with-features") or body
	values = _heading(section)
	grid = section.select_one(".section-features")
	values["columns"] = (grid.get("data-columns") if grid else None) or "3"
	values["features"] = []
	for feature in section.select(".section-feature"):
		link = feature.select_one("a.feature-url")
		content = feature.select_one(".feature-content")
		values["features"].append({
			"title": _text(feature.select_one(".feature-title")),
			"content": _markdown(content, notes) if content else "",
			"url": link.get("href") if link else "",
			"icon": _src(feature.select_one("img.feature-icon")),
		})
	return values


def _collapsible(body, notes):
	section = body.select_one(".section-with-collapsible-content") or body
	values = _heading(section)
	values["align"] = "Center" if "align-center" in (section.get("class") or []) else "Left"
	values["items"] = []
	for item in section.select(".collapsible-item"):
		content = item.select_one(".collapsible-content > div") or item.select_one(".collapsible-content")
		values["items"].append({"title": _text(item.select_one(".collapsible-item-title")),
			"content": _markdown(content, notes) if content else ""})
	return values


def _tabs(body, notes):
	values = _heading(body)
	titles = [_text(link) for link in body.select(".nav-tabs .nav-link")]
	panes = body.select(".tab-content .tab-pane")
	if len(titles) > 6:
		notes.append(f"{len(titles)} tabs, the template holds 6: the rest was left out")
	for index, (title, pane) in enumerate(list(zip(titles, panes))[:6], start=1):
		content = pane.select_one(".from-markdown") or pane
		values[f"tab_{index}_title"] = title
		values[f"tab_{index}_content"] = _markdown(content, notes)
	return values


def _testimonial(body, notes):
	quote = body.select_one(".testimonial") or body
	return {"logo": _src(quote.select_one(".testimonial-logo img")),
		"content": _text(quote.select_one(".testimonial-content")).strip("“”\"").strip(),
		"name": _text(quote.select_one(".testimonial-by"))}


def _full_width_image(body, notes):
	image = body.select_one("img")
	return {"url": _src(image), "description": image.get("alt", "") if image else ""}


PARSERS = {
	"Hero": _hero,
	"Hero with Right Image": _hero_with_right_image,
	"Section with Cards": _cards,
	"Section with Features": _features,
	"Section with Collapsible Content": _collapsible,
	"Section with Tabs": _tabs,
	"Testimonial": _testimonial,
	"Full Width Image": _full_width_image,
}


def _contact(body):
	button = body.find(attrs={"data-wp-contact-open": True})
	label = _text(button)
	button.decompose()
	return {"title": "", "content": _markdown(body, []), "button_label": label, "align": "Left"}


# --- helpers --------------------------------------------------------------------------------------------


def _heading(section):
	return {"title": _text(section.select_one(".section-title")), "subtitle": _text(section.select_one(".section-description"))}


def _subtitle(hero, notes):
	"""The template prints the subtitle as it is: inline HTML (bold, line breaks) stays, text blocks
	(paragraphs, lists from a Rich Text editor) become plain lines."""
	subtitle = hero.select_one(".hero-subtitle")
	if not subtitle:
		return ""
	if subtitle.find(["p", "ul", "ol", "div"]):
		notes.append(f"hero {_text(hero.select_one('.hero-title'))!r}: subtitle had paragraphs, kept as lines")
		return "<br>".join(_text(p) for p in subtitle.find_all(["p", "li"]) if _text(p))
	for tag in subtitle.find_all(["b", "strong"]):
		if not _text(tag):
			tag.unwrap()
	return re.sub(r"\s+", " ", subtitle.decode_contents()).strip()


def _buttons(links):
	values = {}
	for prefix, link in zip(("primary", "secondary"), links):
		values[f"{prefix}_action"] = link.get("href", "")
		values[f"{prefix}_action_label"] = _text(link)
	return values


def _markdown(element, notes):
	html = element.decode_contents()
	tags = {t.name for t in element.find_all(True)}
	if tags - SIMPLE_TAGS - {"div", "section", "article", "center"}:
		notes.append(f"kept as HTML in a Markdown block ({', '.join(sorted(tags - SIMPLE_TAGS))})")
		return html.strip()
	if element.select("[class*=col-], .row"):
		notes.append("rows and columns simplified to plain text")
	return markdownify(html, heading_style="ATX", bullets="-").strip()


def _src(image):
	if not image:
		return ""
	src = image.get("data-src") or image.get("src") or ""
	return "" if src.startswith("data:") else src


def _text(element):
	return " ".join(element.get_text(" ").split()) if element else ""


def _print(report, dry_run):
	print(f"page_builder convert ({'dry run' if int(dry_run) else 'done'}): {len(report)} pages")
	for name, result in report:
		what = "Rich Text" if result.content_type == "Rich Text" else ", ".join(b["web_template"] for b in result.blocks)
		print(f"  {name}: {what}")
		for note in result.notes:
			print(f"      ! {note}")
