"""Small helpers shared by the Web Profile modules (no Frappe request state in here)."""

import hashlib
import re
import unicodedata
from urllib.parse import urlencode

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
