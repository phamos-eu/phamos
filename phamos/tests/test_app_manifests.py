# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Each cockpit must stay installable as its own desktop app (#1458).

Chrome installs a page as a separate app only if it links a valid web app manifest
whose id and scope belong to it alone. A renamed route or a missing icon breaks that
without any visible error, so these tests check the manifests and the files they
point to.
"""

import json
import re
from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase
from PIL import Image

APP_DIR = Path(frappe.get_app_path("phamos"))
REPO_ROOT = APP_DIR.parent
MANIFEST_DIR = APP_DIR / "public" / "manifest"
ASSET_PREFIX = "/assets/phamos/"

# Frontends that link a manifest, and the route each one is served at.
FRONTENDS = {
	"human_resources_frontend": "/human-resources-cockpit",
	"sales_frontend": "/sales-cockpit",
	"accounting_frontend": "/accounting-cockpit",
	"project_management_frontend": "/project-management-cockpit",
	"scan_frontend": "/scan",
}

# Scopes of apps from other Frappe apps on the same site; ours must not overlap them.
OTHER_APP_SCOPES = {"raven": "/raven/", "hrms": "/assets/hrms/frontend/"}


def _asset_path(url):
	"""Map an /assets/phamos/... URL to the file Frappe serves for it."""
	return APP_DIR / "public" / url.removeprefix(ASSET_PREFIX)


def _load_manifests():
	return {path.name: json.loads(path.read_text()) for path in sorted(MANIFEST_DIR.glob("*.webmanifest"))}


class TestAppManifests(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.manifests = _load_manifests()

	def test_each_manifest_meets_install_requirements(self):
		for name, manifest in self.manifests.items():
			with self.subTest(manifest=name):
				for key in ("name", "start_url", "scope", "display", "icons"):
					self.assertTrue(manifest.get(key), f"missing {key}")
				self.assertEqual(manifest["display"], "standalone")
				self.assertTrue(manifest["start_url"].startswith(manifest["scope"]))

				any_sizes = set()
				for icon in manifest["icons"]:
					icon_file = _asset_path(icon["src"])
					self.assertTrue(icon_file.exists(), f"missing {icon['src']}")
					width, height = Image.open(icon_file).size
					self.assertEqual(f"{width}x{height}", icon["sizes"], icon["src"])
					if icon.get("purpose", "any") == "any":
						any_sizes.add(width)
				# Chrome needs a 192 and a 512 px icon to offer the install.
				self.assertTrue({192, 512} <= any_sizes)

	def test_each_app_has_its_own_id_and_scope(self):
		ids = [m.get("id", m["start_url"]) for m in self.manifests.values()]
		self.assertEqual(len(ids), len(set(ids)), "two manifests share an id")

		for name, manifest in self.manifests.items():
			for other_name, other in self.manifests.items():
				if other_name != name:
					with self.subTest(manifest=name, other=other_name):
						self.assertFalse(other["start_url"].startswith(manifest["scope"]))
			for other_app, scope in OTHER_APP_SCOPES.items():
				with self.subTest(manifest=name, other=other_app):
					self.assertFalse(manifest["start_url"].startswith(scope))
					self.assertFalse(scope.startswith(manifest["scope"]))

	def test_each_frontend_links_the_manifest_for_its_route(self):
		manifests_by_url = {f"{ASSET_PREFIX}manifest/{name}": m for name, m in self.manifests.items()}
		for folder, route in FRONTENDS.items():
			with self.subTest(frontend=folder):
				index_html = (REPO_ROOT / folder / "index.html").read_text()
				match = re.search(r'<link rel="manifest" href="([^"]+)"', index_html)
				self.assertIsNotNone(match, "index.html links no manifest")
				self.assertIn(match.group(1), manifests_by_url)
				self.assertEqual(manifests_by_url[match.group(1)]["start_url"], route)

	def test_apps_screen_logos_exist(self):
		for entry in frappe.get_hooks("add_to_apps_screen", app_name="phamos"):
			logo = entry.get("logo", "")
			if logo.startswith(ASSET_PREFIX):
				with self.subTest(app=entry["name"]):
					self.assertTrue(_asset_path(logo).exists(), f"missing {logo}")
