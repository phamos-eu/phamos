"""Generate the web app manifests and icons that make each cockpit installable (#1458).

Chrome only installs a page as its own desktop app when the page links a web app
manifest whose scope is its own. Without one, the cockpits fell back to the app
already installed on the site (Raven). Each cockpit therefore gets a manifest with
its own id, start_url and scope, plus an icon in its own colour so the installed
apps can be told apart in the dock and in cmd+tab.

APPS below is the single source for name, route, colour and symbol; edit it and run
the script again rather than editing the generated files.

Usage (macOS; needs Pillow, which the bench environment has, QuickLook to render
the Feather SVG symbols, and `yarn install` in human_resources_frontend, which
provides the feather-icons package):

	~/frappe-bench/env/bin/python spa_shared/scripts/generate_app_manifests.py [slug ...]

With slugs, only those apps are written (e.g. `idea`).

Writes to phamos/public/manifest/: <slug>.webmanifest, <slug>-icon-192.png,
<slug>-icon-512.png, <slug>-maskable-512.png and <slug>-apple-touch-icon.png.
"""

import json
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = REPO_ROOT / "phamos" / "public" / "manifest"
ASSET_URL = "/assets/phamos/manifest"
FEATHER_ICONS = REPO_ROOT / "human_resources_frontend" / "node_modules" / "feather-icons" / "dist" / "icons"
OWN_SYMBOLS = Path(__file__).resolve().parent / "symbols"  # symbols Feather lacks

# Splash background of an installed cockpit: the cockpit background (frappe-ui surface-gray-1).
LIGHT_BACKGROUND = "#f8f8f8"
# The window title bar (theme_color) is the app's colour (#1933), so cockpits can be told apart
# when switching windows. Cockpit Settings can change it per site; the page's theme-color then
# wins once loaded (phamos/www/spa_boot.py, spa_shared/theme.js). Keep the colours in step with
# COCKPITS in phamos/cockpits/settings.py, which uses them as defaults.

# Tile colours are -700 shades so the white symbol keeps at least 4.5:1 contrast.
# Lead Scan (#2563eb, phamos/public/manifest/scan.webmanifest) keeps its own blue.
APPS = [
	{
		"slug": "ophice",
		"name": "Ophice",
		"description": "Go to work: meet colleagues on the map and open your cockpits",
		"route": "/ophice",
		"color": "#4338ca",
		"symbol": "map",
	},
	{
		"slug": "human-resources",
		"name": "Human Resources",
		"description": "Human Resources issues, tasks and checklists",
		"route": "/human-resources-cockpit",
		"color": "#be123c",
		"symbol": "users",
	},
	{
		"slug": "sales",
		"name": "Sales",
		"description": "Sales issues, tasks and checklists",
		"route": "/sales-cockpit",
		"color": "#c2410c",
		"symbol": "trending-up",
	},
	{
		"slug": "accounting",
		"name": "Accounting",
		"description": "Accounting issues, tasks and receipts",
		"route": "/accounting-cockpit",
		"color": "#047857",
		"symbol": "book-open",
	},
	{
		"slug": "project-management",
		"name": "Project Management",
		"description": "Project Management issues, tasks and implementations",
		"route": "/project-management-cockpit",
		"color": "#6d28d9",
		"symbol": "clipboard",
	},
	{
		"slug": "software-development",
		"name": "Software Development",
		"description": "Software Development issues, tasks and checklists",
		"route": "/software-development-cockpit",
		"color": "#334155",
		"symbol": "code",
	},
	{
		"slug": "general-management",
		"name": "General Management",
		"description": "Company targets, the departments' work and company-wide appointments",
		"route": "/general-management-cockpit",
		"color": "#a16207",
		"symbol": "compass",
	},
	{
		"slug": "implementation",
		"name": "Implementation Cockpit",
		"description": "Status, roadmap, issues and budget of an implementation with phamos",
		"route": "/implementation-cockpit",
		"color": "#0f766e",
		"symbol": "layers",
	},
	{
		"slug": "personal",
		"name": "Personal Cockpit",
		"description": "Issues, tasks and checklists assigned to me",
		"route": "/personal-cockpit",
		"color": "#0e7490",
		"symbol": "user",
	},
	{
		# Idea Catcher (#2202): the phone page that catches an idea. Feather has no bulb, so the
		# symbol is our own SVG in scripts/symbols/ (same 24px grid and stroke as Feather).
		"slug": "idea",
		"name": "Idea",
		"description": "Catch an idea: type or dictate it, link it later",
		"route": "/idea",
		"color": "#ca8a04",
		"symbol": "lightbulb",
	},
]

RENDER_SIZE = 1024  # symbols are rendered large and scaled down for smooth edges
SUPERSAMPLE = 4  # icons are drawn this many times larger, then scaled down


def render_symbol_mask(symbol, workdir):
	"""Render a Feather symbol to a greyscale mask: 255 where the stroke is, 0 elsewhere.

	QuickLook renders the SVG black on white; inverting that gives the mask.
	"""
	own = OWN_SYMBOLS / f"{symbol}.svg"
	svg = (own if own.exists() else FEATHER_ICONS / f"{symbol}.svg").read_text()
	svg = svg.replace('width="24" height="24"', f'width="{RENDER_SIZE}" height="{RENDER_SIZE}"')
	svg = svg.replace('stroke="currentColor"', 'stroke="#000000"')
	svg_path = Path(workdir) / f"{symbol}.svg"
	svg_path.write_text(svg)
	subprocess.run(
		["qlmanage", "-t", "-s", str(RENDER_SIZE), "-o", str(workdir), str(svg_path)],
		check=True,
		capture_output=True,
	)
	rendered = Image.open(f"{svg_path}.png").convert("L")
	return ImageChops.invert(rendered)


def draw_icon(mask, color, size, symbol_share, corner_share=0.0):
	"""Draw a coloured tile with the white symbol centred on it.

	Args:
		mask (Image): symbol mask from render_symbol_mask
		color (str): tile colour as hex
		size (int): output edge length in pixels
		symbol_share (float): symbol size as a share of the tile edge
		corner_share (float): corner radius as a share of the edge; 0 for a full-bleed
			square, which maskable and Apple touch icons need (the OS applies its own shape)

	Returns:
		Image: RGBA icon
	"""
	canvas_size = size * SUPERSAMPLE
	tile = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
	ImageDraw.Draw(tile).rounded_rectangle(
		(0, 0, canvas_size - 1, canvas_size - 1), radius=int(canvas_size * corner_share), fill=color
	)

	symbol_size = int(canvas_size * symbol_share)
	symbol = mask.resize((symbol_size, symbol_size), Image.LANCZOS)
	offset = (canvas_size - symbol_size) // 2
	white = Image.new("RGBA", (symbol_size, symbol_size), (255, 255, 255, 255))
	tile.paste(white, (offset, offset), symbol)

	return tile.resize((size, size), Image.LANCZOS)


def build_manifest(app):
	"""Return the web app manifest for one cockpit."""
	base = f"{ASSET_URL}/{app['slug']}"
	return {
		# id and scope are what make Chrome treat each cockpit as its own app.
		"id": app["route"],
		"name": app["name"],
		"short_name": app["name"],
		"description": app["description"],
		"start_url": app["route"],
		"scope": app["route"],
		"display": "standalone",
		"background_color": LIGHT_BACKGROUND,
		"theme_color": app["color"],
		"icons": [
			{"src": f"{base}-icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
			{"src": f"{base}-icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
			{"src": f"{base}-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
		],
	}


def main(only=None):
	"""Write manifests and icons for all apps, or only for the slugs in `only`."""
	OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
	with tempfile.TemporaryDirectory() as workdir:
		for app in APPS:
			if only and app["slug"] not in only:
				continue
			mask = render_symbol_mask(app["symbol"], workdir)
			slug, color = app["slug"], app["color"]

			# "any" icons: rounded tile, as browsers and the Apps screen show them.
			for size in (192, 512):
				draw_icon(mask, color, size, symbol_share=0.5, corner_share=0.22).save(
					OUTPUT_DIR / f"{slug}-icon-{size}.png"
				)
			# Maskable: full bleed, symbol inside the 80% safe zone the OS may crop to.
			draw_icon(mask, color, 512, symbol_share=0.4).save(OUTPUT_DIR / f"{slug}-maskable-512.png")
			draw_icon(mask, color, 180, symbol_share=0.5).save(OUTPUT_DIR / f"{slug}-apple-touch-icon.png")

			manifest_path = OUTPUT_DIR / f"{slug}.webmanifest"
			manifest_path.write_text(json.dumps(build_manifest(app), indent="\t") + "\n")
			print(f"wrote {manifest_path.relative_to(REPO_ROOT)} and icons")


if __name__ == "__main__":
	import sys

	main(only=sys.argv[1:] or None)
