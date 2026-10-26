"""Social profile links on Person Web Profiles (child table "Employee Profile-Social Media").

Icons come from public/images/social-icons.svg (Tabler Icons, MIT). Only http(s) links are kept,
so nothing like ``javascript:`` can end up in an href.
"""

import re
from urllib.parse import urlparse

SPRITE = "/assets/phamos/images/social-icons.svg"
PLATFORMS = {
	# platform: (sprite symbol, host suffixes used for detection)
	"LinkedIn": ("linkedin", ("linkedin.com",)),
	"GitHub": ("github", ("github.com",)),
	"GitLab": ("gitlab", ("gitlab.com",)),
	"X": ("x", ("x.com", "twitter.com")),
	"YouTube": ("youtube", ("youtube.com", "youtu.be")),
	"Instagram": ("instagram", ("instagram.com",)),
	"Facebook": ("facebook", ("facebook.com",)),
	"Xing": ("xing", ("xing.com",)),
	"Mastodon": ("mastodon", ()),
	"Website": ("website", ()),
}


def normalize_url(url):
	"""'linkedin.com/in/x' -> 'https://linkedin.com/in/x'; None for anything that is not http(s),
	e.g. 'javascript:…' or 'mailto:…' (any other scheme is rejected, not prefixed)."""
	url = (url or "").strip()
	if not url:
		return None
	if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", url):
		url = "https://" + url
	parsed = urlparse(url)
	host = parsed.hostname or ""
	if parsed.scheme not in ("http", "https") or "." not in host or not re.fullmatch(r"[a-z0-9.-]+", host):
		return None
	return url


def detect_platform(url):
	host = (urlparse(url).netloc or "").lower().removeprefix("www.")
	for platform, (_icon, hosts) in PLATFORMS.items():
		if any(host == h or host.endswith("." + h) for h in hosts):
			return platform
	if "/@" in url:  # e.g. https://mastodon.social/@name
		return "Mastodon"
	return "Website"


def social_link(platform, url, label=None):
	icon = PLATFORMS.get(platform, PLATFORMS["Website"])[0]
	return {"platform": platform, "label": label or platform, "url": url, "icon": f"{SPRITE}#social-{icon}"}
