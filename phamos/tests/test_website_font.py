# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""The company font comes from phamos.eu, never from Google (phamos/phamos#2048).

A font loaded from fonts.googleapis.com / fonts.gstatic.com hands every visitor's IP address to
Google and would need consent. Run with
    bench --site <site> run-tests --module phamos.tests.test_website_font
"""

import re
from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase

APP_DIR = Path(frappe.get_app_path("phamos"))
REPO_ROOT = APP_DIR.parent
CSS = APP_DIR / "public" / "css" / "web_profile.bundle.css"
FONT_URL = "/assets/phamos/fonts/questrial/Questrial-Regular.woff2"
GOOGLE = re.compile(r"fonts\.(googleapis|gstatic)\.com")
# built and vendored files are not ours to check; the sources they come from are
SKIP_PARTS = {"node_modules", "dist", ".git", "assets", "__pycache__", "frontend"}


class TestWebsiteFont(FrappeTestCase):
	def test_questrial_is_served_from_the_app(self):
		css = CSS.read_text()
		face = re.search(r"@font-face\s*{[^}]*}", css)
		self.assertIsNotNone(face, "web_profile.bundle.css declares the font")
		self.assertIn('font-family: "Questrial"', face.group(0))
		self.assertIn(FONT_URL, face.group(0))
		font = APP_DIR / "public" / FONT_URL.removeprefix("/assets/phamos/")
		self.assertTrue(font.exists(), f"missing {font}")
		self.assertEqual(font.read_bytes()[:4], b"wOF2")
		self.assertTrue((font.parent / "OFL.txt").exists(), "the licence ships with the font")

	def test_website_pages_use_questrial_first(self):
		# [^;}]: the last declaration of a rule needs no semicolon (review of !1292)
		stacks = re.findall(r"font-family:\s*([^;}]+)", CSS.read_text())
		self.assertTrue(stacks)
		for stack in stacks:
			if re.search(r"\bInter\b", stack):
				self.assertTrue(stack.strip().startswith("Questrial"), stack)

	def test_frappe_font_variable_keeps_questrial_without_the_theme_font(self):
		"""Frappe styles html/body and Web Page text with var(--font-stack); the theme sets Questrial in it
		only while its Google Font field is filled, which is emptied to stop the request to Google."""
		# every :root rule, not only the first; [^;}]: no semicolon needed on the last declaration
		stacks = [
			m.group(1).strip()
			for block in re.finditer(r":root\s*{([^}]*)}", CSS.read_text())
			for m in re.finditer(r"--font-stack:\s*([^;}]+)", block.group(1))
		]
		self.assertTrue(stacks, "web_profile.bundle.css sets --font-stack")
		for stack in stacks:
			self.assertTrue(stack.startswith('"Questrial"'), stack)

	def test_nothing_in_the_app_loads_fonts_from_google(self):
		offenders, scanned = [], 0
		for root in (APP_DIR / "public", APP_DIR / "templates", APP_DIR / "www"):
			for file in root.rglob("*"):
				# parts below the scanned folder: a checkout that lives in a folder named "dist" or
				# "frontend" must not skip everything (review of !1292)
				if file.suffix not in {".css", ".scss", ".html", ".js", ".vue"} or SKIP_PARTS & set(file.relative_to(root).parts):
					continue
				scanned += 1
				if GOOGLE.search(file.read_text(errors="ignore")):
					offenders.append(str(file.relative_to(REPO_ROOT)))
		self.assertGreater(scanned, 10, "the scan must look at the app's files, not pass on an empty list")
		self.assertEqual(offenders, [])
