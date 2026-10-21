"""Server-side filtering, counting, sorting and pagination for every Web Profile listing page.

Filters live in the URL (``?department=a&department=b&page=2``), so every filtered view can be
linked, shared and crawled, and the page works without JavaScript. Within one facet the values
are OR-ed, across facets AND-ed. Option counts follow the usual faceted-search rule: an option's
count is computed with all *other* facets applied, so selecting an option never zeroes its siblings.

Items are filtered in Python. The sections hold hundreds of records at most, which keeps this
simple; move to SQL only if a section ever grows into the thousands.
"""

import math

import frappe
from frappe import _

from phamos.web_profile.icons import flag_url
from phamos.web_profile.sections import CACHE_KEY, CACHE_SECONDS, SECTIONS, build_profile, get_items, section_url
from phamos.web_profile.utils import build_query

PAGE_SIZE = 24  # override per site with `bench set-config web_profile_page_size 4` to test paging
SCROLL_FACET_THRESHOLD = 8  # facets with more options render in a scrolling box


def read_params(section):
	"""Selected facet values, search, sort and page from the request (repeated keys allowed)."""
	args = frappe.request.args if getattr(frappe.local, "request", None) else {}
	getlist = args.getlist if hasattr(args, "getlist") else (lambda k: [args[k]] if k in args else [])
	config = SECTIONS[section]

	selected, ranges = {}, {}
	for facet in config["facets"]:
		if facet["type"] == "range":
			# Min/max slider: ?tenure_min=2&tenure_max=5 (either end may be missing).
			bounds = []
			for end in ("min", "max"):
				try:
					bounds.append(int((getlist(f"{facet['key']}_{end}") or [""])[0]))
				except ValueError:
					bounds.append(None)
			if bounds != [None, None]:
				ranges[facet["key"]] = bounds
			continue
		values = [v for v in getlist(facet["key"]) if v]
		if facet["type"] == "toggle":
			allowed = [o[0] for o in facet["options"]]
			values = [v for v in values[:1] if v in allowed] or [facet["default"]]
		if values:
			selected[facet["key"]] = list(dict.fromkeys(values))

	sort_keys = [s[0] for s in config["sorts"]]
	sort = (getlist("sort") or [""])[0]
	try:
		page = max(1, int((getlist("page") or ["1"])[0]))
	except ValueError:
		page = 1
	return {
		"selected": selected,
		"ranges": ranges,
		"q": ((getlist("q") or [""])[0] or "").strip(),
		"sort": sort if sort in sort_keys else sort_keys[0],
		"page": page,
	}


_FOLD = str.maketrans({"ä": "a", "ö": "o", "ü": "u", "ß": "ss", "é": "e", "è": "e", "á": "a", "à": "a", "ó": "o", "ç": "c"})


def _fold(text):
	"""Case- and umlaut-insensitive: 'Müller', 'Mueller' and 'Muller' all become 'muller'."""
	text = (text or "").casefold()
	return text.replace("ae", "a").replace("oe", "o").replace("ue", "u").translate(_FOLD)


def search_texts(section, lang):
	"""{item name: folded text} with everything a visitor can read on each detail page.

	Built from what the page renders (build_profile), so anonymised details can never be found.
	Cached alongside the items and reset together with them whenever a profile changes.
	"""
	field = f"search:{section}:{lang}"
	texts = frappe.cache.hget(CACHE_KEY, field)
	if texts is None:
		texts = {}
		for item in get_items(section, lang):
			profile = build_profile(item, lang)
			parts = [item.title, item.subtitle, item.summary, frappe.utils.strip_html(item.body or ""), profile["overview"],
				*item.chips, *(link["label"] for link in item.socials)]
			for key, labels in item.labels.items():
				parts += [label for value, label in labels.items() if value in item.facets.get(key, [])]
			for fact in profile["facts"]:
				parts += [fact["label"], fact.get("value") or ""] + [link["value"] for link in fact.get("links") or []]
			for block in profile["related"]:
				parts += [block["title"], block.get("intro") or ""]
				for tile in block["tiles"]:
					parts += [tile.title, tile.subtitle, *tile.chips]
			for card in profile["key_people"]:
				parts += [card["person"].title, card.get("role") or ""]
			texts[item.name] = _fold(" ".join(str(p) for p in parts if p))
		frappe.cache.hset(CACHE_KEY, field, texts)
		frappe.cache.expire(CACHE_KEY, CACHE_SECONDS)
	return texts


def _matches(item, selected, q, skip=None, ranges=None, texts=None):
	if q:
		haystack = (texts or {}).get(item.name) or _fold(item.search)
		# Every word must appear somewhere on the page, in any order.
		if not all(word in haystack for word in _fold(q).split()):
			return False
	for key, values in selected.items():
		if key != skip and not set(item.facets.get(key, [])) & set(values):
			return False
	for key, (low, high) in (ranges or {}).items():
		value = item.numbers.get(key)
		if key == skip:
			continue
		# An active range leaves out records without that number (e.g. tenure of customer contacts).
		if value is None or (low is not None and value < low) or (high is not None and value > high):
			return False
	return True


def _query(section, params, **overrides):
	"""Query string for the current state with ``overrides`` applied (defaults dropped for clean URLs)."""
	state = {**params["selected"], "q": params["q"], "sort": params["sort"], "page": params["page"]}
	for key, (low, high) in params["ranges"].items():
		state[f"{key}_min"], state[f"{key}_max"] = low, high
	state.update(overrides)
	for facet in SECTIONS[section]["facets"]:
		if facet["type"] == "toggle" and state.get(facet["key"]) == [facet["default"]]:
			state[facet["key"]] = None
	if state.get("sort") == SECTIONS[section]["sorts"][0][0]:
		state["sort"] = None
	if state.get("page") == 1:
		state["page"] = None
	return build_query(state)


def build_listing(section, lang):
	config = SECTIONS[section]
	params = read_params(section)
	items = get_items(section, lang)
	selected, q, ranges = params["selected"], params["q"], params["ranges"]

	# Slider bounds come from all records; a range covering the full span is no filter at all.
	bounds = {}
	for facet in config["facets"]:
		if facet["type"] == "range":
			values = [i.numbers[facet["key"]] for i in items if i.numbers.get(facet["key"]) is not None]
			if values:
				bounds[facet["key"]] = (min(values), max(values))
	for key in list(ranges):
		low, high = ranges[key]
		span = bounds.get(key)
		if not span:
			ranges.pop(key)
			continue
		clamp = lambda v, default: min(max(v, span[0]), span[1]) if v is not None else default  # noqa: E731
		low, high = clamp(low, span[0]), clamp(high, span[1])
		low, high = min(low, high), max(low, high)
		if (low, high) == span:
			ranges.pop(key)
		else:
			ranges[key] = [low, high]

	texts = search_texts(section, lang) if q else None
	results = [i for i in items if _matches(i, selected, q, ranges=ranges, texts=texts)]
	results.sort(key=lambda i: i.sort.get(params["sort"], i.sort["name"]))

	facets = []
	for facet in config["facets"]:
		key = facet["key"]
		base = [i for i in items if _matches(i, selected, q, skip=key, ranges=ranges, texts=texts)]
		if facet["type"] == "range":
			span = bounds.get(key)
			in_view = [i.numbers[key] for i in base if i.numbers.get(key) is not None]
			if not span or span[0] == span[1] or (not in_view and key not in ranges):
				continue  # nothing to slide in this view
			low, high = ranges.get(key, span)
			facets.append({
				"key": key, "label": _(facet["label"]), "type": "range",
				"min": span[0], "max": span[1], "low": low, "high": high,
				"unit": _(facet["unit"]) if facet.get("unit") else "",
				"active": key in ranges,
			})
			continue
		if facet.get("options"):
			options = [(value, _(label)) for value, label in facet["options"]]
		else:
			labels = {}
			for i in items:
				labels.update(i.labels.get(key, {}))
			options = sorted(labels.items(), key=lambda o: (o[1] or "").lower())
			if key in ("year", "founded"):
				options.sort(key=lambda o: o[0], reverse=True)
		if not options:
			continue
		chosen = selected.get(key, [])
		counts = {value: sum(1 for i in base if value in i.facets.get(key, [])) for value, _label in options}
		if facet["type"] != "toggle" and not chosen and not any(counts.values()):
			continue  # nothing to pick in this view (e.g. tenure while browsing customers and partners)
		facets.append({
			"key": key,
			"label": _(facet["label"]),
			"type": facet["type"],
			"default": facet.get("default"),
			"scroll": len(options) > SCROLL_FACET_THRESHOLD,
			"options": [{
				"value": value,
				"label": label,
				"count": counts[value],
				"checked": value in chosen,
				"flag": flag_url(value) if key == "language" else None,
			} for value, label in options],
			"active": bool(chosen) and facet["type"] != "toggle",
		})

	page_size = int(frappe.conf.get("web_profile_page_size") or PAGE_SIZE)
	pages = max(1, math.ceil(len(results) / page_size))
	page = min(params["page"], pages)
	page_items = results[(page - 1) * page_size : page * page_size]

	active_filters = []
	for facet in facets:
		if facet["type"] == "toggle":
			continue
		if facet["type"] == "range":
			if facet["active"]:
				active_filters.append({
					"label": f"{facet['label']}: " + (str(facet["low"]) if facet["low"] == facet["high"]
						else f"{facet['low']}–{facet['high']}") + (f" {facet['unit']}" if facet["unit"] else ""),
					"url": section_url(section, lang) + _query(section, params, **{f"{facet['key']}_min": None,
						f"{facet['key']}_max": None, "page": 1}),
				})
			continue
		for option in facet["options"]:
			if option["checked"]:
				remaining = [v for v in selected[facet["key"]] if v != option["value"]]
				active_filters.append({
					"label": f"{facet['label']}: {option['label']}",
					"url": section_url(section, lang) + _query(section, params, **{facet["key"]: remaining, "page": 1}),
				})
	if q:
		active_filters.append({"label": f"“{q}”", "url": section_url(section, lang) + _query(section, params, q="", page=1)})

	base_url = section_url(section, lang)
	singular, plural = config["noun"]
	return {
		"params": params,
		"facets": facets,
		"results": page_items,
		"total": len(results),
		"count_label": _("1 {0}").format(_(singular)) if len(results) == 1 else _("{0} {1}").format(len(results), _(plural)),
		"page": page,
		"pages": pages,
		"next_url": base_url + _query(section, params, page=page + 1) if page < pages else None,
		"prev_url": base_url + _query(section, params, page=page - 1) if page > 1 else None,
		"clear_url": base_url,
		"active_filters": active_filters,
		"default_sort": config["sorts"][0][0],
		"sorts": [{"value": v, "label": _(label), "selected": v == params["sort"]} for v, label in config["sorts"]],
		"has_filters": bool(active_filters),
		# Filtered and paged views point search engines at the plain list.
		"is_filtered": bool(active_filters) or bool(ranges) or page > 1 or params["sort"] != config["sorts"][0][0]
			or selected != {f["key"]: [f["default"]] for f in config["facets"] if f["type"] == "toggle"},
	}
