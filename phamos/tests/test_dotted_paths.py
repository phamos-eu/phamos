"""Fail CI when a ``phamos.*`` dotted path points at code that Python can't find.

Frappe resolves hooks, patches and ``frappe.call`` methods by dotted path at run
time, so a missing function only shows up on the live site. On 2026-09-23 every
portal page load failed with "module 'phamos.api' has no attribute
'get_popup_doctypes'": ``phamos/api.py`` and the package ``phamos/api/`` both
existed, Python loads the package, and every function in ``api.py`` was gone
(#1413, fixed by !858).

The paths are checked by reading files (AST), not by importing them, so the test
needs no data and does not run module code. Modules are resolved the way Python
resolves them: a package wins over a module file of the same name.

Based on suncycle's ``test_import_paths`` (suncycle/suncycle#2614).
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase

APP = "phamos"
DOTTED_PATH_RE = re.compile(r"^phamos(?:\.[A-Za-z_][A-Za-z0-9_]*){2,}$")
QUOTED_PATH_RE = re.compile(r"""['"`](phamos(?:\.[A-Za-z_][A-Za-z0-9_]*){2,})['"`]""")
PATCH_EXECUTE_RE = re.compile(r"from\s+(phamos(?:\.\w+)+)\s+import\s+(\w+)")

# Folders with client code that calls phamos methods; built output and
# node_modules are left out.
CLIENT_SOURCE_DIRS = (
	"phamos",
	"frontend/src",
	"accounting_frontend/src",
	"human_resources_frontend/src",
	"personal_frontend/src",
	"project_management_frontend/src",
	"sales_frontend/src",
	"scan_frontend/src",
	"software_development_frontend/src",
	"spa_shared",
)
CLIENT_SUFFIXES = (".js", ".vue", ".ts")
SKIP_DIRS = {"node_modules", "__pycache__", "dist", "frontend"}

# Broken paths that are already known, with where they get fixed. Remove an
# entry with its fix: test_known_broken_paths_are_still_broken fails until then.
KNOWN_BROKEN = {
	# Team "after_save" hook: no such function, and not a Frappe doc event (#1598).
	"phamos.phamos.doctype.team.team.create_team_capacity_ledger_entry": "#1598",
	# Extract PDF page imports the PDF Party Rule doctype, which was never committed (49ce2493).
	"phamos.phamos.doctype.pdf_party_rule.pdf_party_rule.get_party_rules": "49ce2493",
	"phamos.phamos.doctype.pdf_party_rule.pdf_party_rule.replace_party_rules": "49ce2493",
}

HOOK_FILE_ATTRS = (
	"app_include_js",
	"app_include_css",
	"web_include_js",
	"web_include_css",
	"doctype_js",
	"doctype_list_js",
	"doctype_tree_js",
	"doctype_calendar_js",
	"page_js",
)


@dataclass(frozen=True)
class PathRef:
	file: Path
	lineno: int
	path: str


def _app_path() -> Path:
	"""``.../apps/phamos/phamos``: the Python package."""
	return Path(frappe.get_app_path(APP))


def _repo_path() -> Path:
	return _app_path().parent


def _rel(file_path: Path) -> str:
	return str(file_path.relative_to(_repo_path()))


def _iter_files(root: Path, suffixes: tuple[str, ...], skip_dirs=frozenset({"__pycache__"})):
	if not root.is_dir():
		return
	for file_path in sorted(root.rglob("*")):
		if file_path.suffix not in suffixes or not file_path.is_file():
			continue
		if skip_dirs.intersection(file_path.relative_to(root).parts[:-1]):
			continue
		yield file_path


def _iter_python_files():
	for file_path in _iter_files(_app_path(), (".py",)):
		if file_path.name.startswith("test_"):
			continue
		yield file_path


def _iter_client_files():
	# "frontend" and "dist" under phamos/public hold built bundles, not sources.
	for folder in CLIENT_SOURCE_DIRS:
		yield from _iter_files(_repo_path() / folder, CLIENT_SUFFIXES, frozenset(SKIP_DIRS))


def _module_file(module_name: str) -> Path | None:
	"""The file Python loads for ``module_name``, or None.

	Same order as Python's path finder: a package (folder with ``__init__.py``)
	wins over ``<name>.py``, which wins over a folder without ``__init__.py``
	(a namespace package, such as ``phamos/events``). A namespace package is
	returned as its folder.
	"""
	parts = module_name.split(".")
	if parts[0] != APP:
		return None
	current = _app_path()
	for index, part in enumerate(parts[1:], start=1):
		folder = current / part
		if (folder / "__init__.py").is_file():
			current = folder
			continue
		module = current / f"{part}.py"
		if module.is_file():
			return module if index == len(parts) - 1 else None
		if folder.is_dir():
			current = folder
			continue
		return None
	init = current / "__init__.py"
	return init if init.is_file() else current


@cache
def _top_level_names(file_path: Path) -> frozenset[str] | None:
	"""Names a module defines at top level; None if it has a star import."""
	tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
	names: set[str] = set()
	for node in tree.body:
		if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
			names.add(node.name)
		elif isinstance(node, ast.Assign):
			for target in node.targets:
				# "A = ..." and "A, B = ..."
				names.update(n.id for n in ast.walk(target) if isinstance(n, ast.Name))
		elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
			names.add(node.target.id)
		elif isinstance(node, (ast.Import, ast.ImportFrom)):
			for alias in node.names:
				if alias.name == "*":
					return None
				names.add(alias.asname or alias.name.split(".")[0])
		elif isinstance(node, (ast.If, ast.Try)):
			# Names defined in a top-level if/try (optional imports, fallbacks).
			for child in ast.walk(node):
				if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
					names.add(child.name)
				elif isinstance(child, ast.Assign):
					names.update(n.id for t in child.targets for n in ast.walk(t) if isinstance(n, ast.Name))
				elif isinstance(child, (ast.Import, ast.ImportFrom)):
					names.update(a.asname or a.name.split(".")[0] for a in child.names)
	return frozenset(names)


def _check_path(path: str) -> str | None:
	"""None if ``path`` names a phamos module or a top-level name in one, else why not."""
	if _module_file(path):
		return None
	module_name, _, attr = path.rpartition(".")
	module_file = _module_file(module_name)
	if module_file is None:
		return f"no module {module_name!r}"
	if module_file.is_dir():
		return f"no module {path!r}"
	names = _top_level_names(module_file)
	if names is None or attr in names:
		return None
	return f"{_rel(module_file)} has no {attr!r}"


def _collect_failures(refs: list[PathRef]) -> list[str]:
	failures = []
	for ref in refs:
		if ref.path in KNOWN_BROKEN:
			continue
		if error := _check_path(ref.path):
			failures.append(f"- {_rel(ref.file)}:{ref.lineno} {ref.path}: {error}")
	return failures


def _hook_paths() -> list[PathRef]:
	"""Every phamos dotted path in hooks.py, with its line."""
	hooks_file = _app_path() / "hooks.py"
	tree = ast.parse(hooks_file.read_text(encoding="utf-8"))
	return [
		PathRef(hooks_file, node.lineno, node.value)
		for node in ast.walk(tree)
		if isinstance(node, ast.Constant)
		and isinstance(node.value, str)
		and DOTTED_PATH_RE.match(node.value)
	]


def _patch_paths() -> list[PathRef]:
	patches_txt = _app_path() / "patches.txt"
	refs = []
	for lineno, raw in enumerate(patches_txt.read_text(encoding="utf-8").splitlines(), 1):
		line = raw.split("#", 1)[0].strip()
		if not line or line.startswith("["):
			continue
		if line.startswith("execute:"):
			refs.extend(
				PathRef(patches_txt, lineno, f"{module}.{name}")
				for module, name in PATCH_EXECUTE_RE.findall(line)
			)
			continue
		refs.append(PathRef(patches_txt, lineno, f"{line.split()[0]}.execute"))
	return refs


def _python_paths() -> list[PathRef]:
	"""``from phamos.x import y`` / ``import phamos.x`` and dotted strings such as
	``frappe.enqueue("phamos.x.fn")`` in phamos Python code."""
	refs = []
	for file_path in _iter_python_files():
		tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
		for node in ast.walk(tree):
			if isinstance(node, ast.Import):
				refs.extend(
					PathRef(file_path, node.lineno, alias.name)
					for alias in node.names
					if alias.name.startswith(f"{APP}.")
				)
			elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
				if node.module != APP and not node.module.startswith(f"{APP}."):
					continue
				refs.extend(
					PathRef(file_path, node.lineno, f"{node.module}.{alias.name}")
					for alias in node.names
					if alias.name != "*"
				)
			elif (
				isinstance(node, ast.Constant)
				and isinstance(node.value, str)
				and DOTTED_PATH_RE.match(node.value)
			):
				refs.append(PathRef(file_path, node.lineno, node.value))
	return refs


def _client_paths() -> list[PathRef]:
	"""Quoted ``phamos.*`` paths in JS / Vue / TS: ``frappe.call`` methods,
	``createResource`` urls and the like."""
	refs = []
	for file_path in _iter_client_files():
		for lineno, line in enumerate(file_path.read_text(encoding="utf-8").splitlines(), 1):
			if line.lstrip().startswith(("//", "*", "/*")):
				continue
			refs.extend(
				PathRef(file_path, lineno, match) for match in QUOTED_PATH_RE.findall(line)
			)
	return refs


def _hook_file_values():
	import phamos.hooks as hooks

	for attr in HOOK_FILE_ATTRS:
		value = getattr(hooks, attr, None)
		values = value.values() if isinstance(value, dict) else [value]
		for item in values:
			for path in item if isinstance(item, (list, tuple)) else [item]:
				if isinstance(path, str):
					yield attr, path


def _hook_file_exists(path: str) -> bool:
	app = _app_path()
	if path.startswith(f"/assets/{APP}/"):
		return (app / "public" / path.removeprefix(f"/assets/{APP}/")).exists()
	if path.startswith(("/", "http")):
		return True
	if ".bundle." in path:
		# esbuild entry points live anywhere under public/ ("x.bundle.js" or "x.bundle.css").
		stem = path.rsplit(".", 1)[0]
		return any((app / "public").rglob(f"{stem}.*"))
	return (app / path).exists()


class TestDottedPaths(FrappeTestCase):
	def test_no_module_is_shadowed_by_a_package(self):
		"""``x.py`` next to a package ``x/`` is never loaded: its code is unreachable (#1413)."""
		shadowed = [
			_rel(package / "__init__.py") + f" hides {_rel(package.with_suffix('.py'))}"
			for package in (init.parent for init in _app_path().rglob("__init__.py"))
			if package.with_suffix(".py").is_file()
		]
		self.assertFalse(
			shadowed, "Modules hidden by a package of the same name:\n- " + "\n- ".join(shadowed)
		)

	def test_hooks_paths_resolve(self):
		refs = _hook_paths()
		self.assertIn("phamos.website.get_website_user_home_page", {ref.path for ref in refs})
		failures = _collect_failures(refs)
		self.assertFalse(failures, "Broken paths in hooks.py:\n" + "\n".join(failures))

	def test_patch_paths_resolve(self):
		failures = _collect_failures(_patch_paths())
		self.assertFalse(failures, "Broken patches in patches.txt:\n" + "\n".join(failures))

	def test_python_imports_and_paths_resolve(self):
		failures = _collect_failures(_python_paths())
		self.assertFalse(failures, "Broken phamos imports or paths in Python:\n" + "\n".join(failures))

	def test_client_method_paths_resolve(self):
		refs = _client_paths()
		self.assertIn("phamos.api.get_popup_doctypes", {ref.path for ref in refs})
		failures = _collect_failures(refs)
		self.assertFalse(failures, "Broken phamos methods called from JS / Vue:\n" + "\n".join(failures))

	def test_known_broken_paths_are_still_broken(self):
		fixed = [f"- {path} ({ref})" for path, ref in KNOWN_BROKEN.items() if _check_path(path) is None]
		self.assertFalse(fixed, "Fixed now, remove them from KNOWN_BROKEN:\n" + "\n".join(fixed))

	def test_hook_asset_files_exist(self):
		missing = [f"- {attr}: {path}" for attr, path in _hook_file_values() if not _hook_file_exists(path)]
		self.assertFalse(missing, "Files named in hooks.py that don't exist:\n" + "\n".join(missing))
