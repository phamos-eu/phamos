"""Small helpers shared by the Web Profile modules (no Frappe request state in here)."""

import hashlib
import re
import unicodedata
from urllib.parse import urlencode, urlparse

# Legal forms dropped to find the bare company name ("Nordwerk Maschinenbau GmbH" -> "Nordwerk Maschinenbau").
LEGAL_FORMS = re.compile(
	r"(&\s*co\.?|\b(gmbh|mbh|ag|kg|kgaa|ohg|gbr|ug|se|e\.\s?k\.|ltd|llc|inc|pvt|plc|corp|s\.a|s\.r\.l|b\.v)\b)\.?",
	re.IGNORECASE,
)
_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "ae", "Ö": "oe", "Ü": "ue", "ß": "ss"})


def slugify(value):
	"""'Hans Müller & Co.' -> 'hans-mueller-co' (German transliteration, ASCII only)."""
	value = str(value or "").translate(_UMLAUTS)
	value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
	value = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
	return value


def short_hash(value, length=6):
	"""Deterministic, non-reversible suffix for anonymous routes."""
	return hashlib.sha1(str(value).encode()).hexdigest()[:length]


def build_query(params):
	"""Query string from {key: value | [values]}, dropping empty values; '' when nothing is left."""
	pairs = []
	for key, value in params.items():
		for v in value if isinstance(value, list | tuple) else [value]:
			if v not in (None, "", []):
				pairs.append((key, v))
	return ("?" + urlencode(pairs)) if pairs else ""


def initials(title):
	parts = [p for p in re.split(r"\s+", title or "") if p]
	return "".join(p[0] for p in parts[:2]).upper() or "–"


def identifying_terms(name, website=None):
	"""What an anonymous page's texts and any public URL must not contain for a company: its name, the
	name without legal form, its website domain and the domain's first label (if specific enough)."""
	terms = []
	name = " ".join((name or "").split())
	if name:
		terms.append(name)
		bare = " ".join(LEGAL_FORMS.sub(" ", name).replace(",", " ").split()).strip(" -&")
		if len(bare) >= 3 and bare != name:
			terms.append(bare)
	website = (website or "").strip()
	if website:
		host = (urlparse(website if "://" in website else "https://" + website).hostname or "").removeprefix("www.")
		if host:
			terms.append(host)
			label = host.split(".")[0]
			if len(label) >= 4:
				terms.append(label)
	return terms


def slug_contains(slug, terms):
	"""Whether ``slug`` contains one of ``terms`` as whole slug words ("handel-dach" has "dach", not "da")."""
	padded = f"-{slug}-"
	return any(f"-{term}-" in padded for term in map(slugify, terms) if term)
