"""Module icons and language flags for the Web Profile pages.

Module icons are ERPNext's own workspace icons: the Frappe "timeless" SVG sprite that the desk
sidebar uses, referenced by the icon name of the linked Workspace (Accounting -> "accounting").
Flags are the SVGs from flag-icons (MIT, see public/images/flags/LICENSE-flag-icons.txt), served
locally. A language is not a nation, so LANGUAGE_FLAGS picks the usual flag for each language.
"""

import os
import re

import frappe

ICON_SPRITE = "/assets/frappe/icons/timeless/icons.svg"
FLAG_PATH = "/assets/phamos/images/flags/{0}.svg"

# Language code (Frappe Language) -> ISO country code of the flag shown for it.
LANGUAGE_FLAGS = {
	"de": "de", "en": "gb", "es": "es", "fr": "fr", "it": "it", "pt": "pt", "pt-BR": "pt", "nl": "nl",
	"pl": "pl", "tr": "tr", "ru": "ru", "uk": "ua", "ar": "sa", "ur": "pk", "hi": "in", "pa": "in", "ta": "in",
	"am": "et", "om": "et", "sw": "ke", "zh": "cn", "zh-TW": "cn", "ja": "jp", "ko": "kr", "sv": "se", "da": "dk",
	"no": "no", "nb": "no", "fi": "fi", "cs": "cz", "sk": "sk", "hu": "hu", "ro": "ro", "el": "gr", "he": "il",
	"fa": "ir", "bn": "bd", "vi": "vn", "th": "th", "id": "id", "tl": "ph", "ms": "my",
}


def flag_url(language):
	country = LANGUAGE_FLAGS.get(language) or LANGUAGE_FLAGS.get((language or "").split("-")[0])
	if country and os.path.exists(frappe.get_app_path("phamos", "public", "images", "flags", f"{country}.svg")):
		return FLAG_PATH.format(country)
	return None


def _sprite_icons():
	"""Symbol ids available in the Frappe sprite, read once per process."""
	cached = getattr(_sprite_icons, "ids", None)
	if cached is None:
		path = frappe.get_app_path("frappe", "public", "icons", "timeless", "icons.svg")
		try:
			with open(path) as f:
				cached = set(re.findall(r'id="icon-([\w-]+)"', f.read()))
		except OSError:
			cached = set()
		_sprite_icons.ids = cached
	return cached


def module_icon(icon):
	"""Sprite URL fragment for an ERPNext workspace icon, or None if the sprite doesn't have it."""
	if icon and icon in _sprite_icons():
		return f"{ICON_SPRITE}#icon-{icon}"
	return None
