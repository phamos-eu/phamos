# Copyright (c) 2026, phamos.eu and Contributors
# See license.txt

"""Fail CI when a dotted phamos path no longer exists.

Only ``phamos.*`` files and attributes are checked (AST, no importing optional apps).
Catches missing hooks such as ``phamos.mailcow_integration.caldav.sync_event.on_upsert``.

Run:
	bench --site <site> run-tests --app phamos --module phamos.tests.test_import_paths
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase

DOTTED_PATH_RE = re.compile(r"^phamos(?:\.[A-Za-z_][A-Za-z0-9_]*){2,}$")
QUOTED_PATH_RE = re.compile(r"""['"](phamos(?:\.[A-Za-z_][A-Za-z0-9_]*){2,})['"]""")

# JS-only namespaces (frappe.provide), not Python modules.
SKIP_PATH_PREFIXES = ("phamos.frappe.",)
ASSET_SUFFIXES = (".js", ".css", ".scss", ".json", ".html", ".png", ".svg", ".bundle.js")

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

KNOWN_HOOK_PATH = "phamos.mailcow_integration.caldav.sync_event.on_upsert"


@dataclass(frozen=True)
class PathRef:
	file: Path
	lineno: int
	path: str
	kind: str


def _get_phamos_app_path() -> Path:
	return Path(frappe.get_app_path("phamos"))


def _rel(file_path: Path) -> str:
	return str(file_path.relative_to(_get_phamos_app_path()))


def _iter_phamos_files(*suffixes: str, include_tests: bool = False):
	app_path = _get_phamos_app_path()
	for file_path in sorted(app_path.rglob("*")):
		if not file_path.is_file() or file_path.suffix not in suffixes:
			continue
		if "__pycache__" in file_path.parts:
			continue
		if not include_tests and (
			file_path.name.startswith("test_") or file_path.name.startswith("_ui_test_")
		):
			continue
		yield file_path


def _looks_like_dotted_python_path(value: str) -> bool:
	if not DOTTED_PATH_RE.match(value):
		return False
	if any(value.startswith(prefix) for prefix in SKIP_PATH_PREFIXES):
		return False
	if value.endswith(ASSET_SUFFIXES):
		return False
	if "/" in value or " " in value or "@" in value:
		return False
	return True


def _module_file_candidates(module_name: str) -> list[Path]:
	app_path = _get_phamos_app_path()
	parts = module_name.split(".")[1:]
	if not parts:
		return [app_path / "__init__.py"]
	rel = Path(*parts)
	return [app_path / rel.with_suffix(".py"), app_path / rel / "__init__.py"]


def _find_phamos_module_file(module_name: str) -> Path | None:
	for candidate in _module_file_candidates(module_name):
		if candidate.is_file():
			return candidate
	return None


def _top_level_names(file_path: Path) -> set[str]:
	tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
	names: set[str] = set()
	for node in tree.body:
		if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
			names.add(node.name)
		elif isinstance(node, ast.Assign):
			for target in node.targets:
				if isinstance(target, ast.Name):
					names.add(target.id)
		elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
			names.add(node.target.id)
		elif isinstance(node, (ast.Import, ast.ImportFrom)):
			for alias in node.names:
				if alias.name == "*":
					continue
				names.add(alias.asname or alias.name.split(".")[0])
	return names


def _assert_phamos_path_exists(path: str) -> None:
	"""Check that a ``phamos.*`` module file (and optional attribute) exists.

	Inspects files with AST so optional apps are not imported.
	"""
	if not path.startswith("phamos.") and path != "phamos":
		return

	if _find_phamos_module_file(path):
		return

	if "." not in path:
		raise ModuleNotFoundError(f"No module named {path!r}")

	modulename, attr = path.rsplit(".", 1)
	module_file = _find_phamos_module_file(modulename)
	if module_file is None:
		raise ModuleNotFoundError(f"No module named {modulename!r}")
	if attr not in _top_level_names(module_file):
		raise ImportError(f"cannot import name {attr!r} from {modulename!r}")


def _py_file_to_module(file_path: Path) -> str:
	rel = file_path.relative_to(_get_phamos_app_path())
	parts = list(rel.with_suffix("").parts)
	if parts[-1] == "__init__":
		parts = parts[:-1]
	return ".".join(["phamos", *parts])


def _collect_phamos_imports(file_path: Path) -> list[PathRef]:
	tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
	refs: list[PathRef] = []

	for node in ast.walk(tree):
		if isinstance(node, ast.Import):
			for alias in node.names:
				if alias.name == "phamos" or alias.name.startswith("phamos."):
					refs.append(
						PathRef(file_path, node.lineno, alias.name, "import")
					)
		elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
			if node.module != "phamos" and not node.module.startswith("phamos."):
				continue
			imported = [alias.name for alias in node.names if alias.name != "*"]
			if not imported:
				refs.append(PathRef(file_path, node.lineno, node.module, "import"))
				continue
			for name in imported:
				refs.append(
					PathRef(
						file_path,
						node.lineno,
						f"{node.module}.{name}",
						"import",
					)
				)

	return refs


def _collect_string_paths_from_python(file_path: Path) -> list[PathRef]:
	tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
	refs: list[PathRef] = []

	for node in ast.walk(tree):
		value = None
		if isinstance(node, ast.Constant) and isinstance(node.value, str):
			value = node.value
		if not value or not _looks_like_dotted_python_path(value):
			continue
		refs.append(PathRef(file_path, node.lineno, value, "string"))

	return refs


def _collect_quoted_paths_from_text(file_path: Path) -> list[PathRef]:
	refs: list[PathRef] = []
	for lineno, line in enumerate(file_path.read_text(encoding="utf-8").splitlines(), 1):
		code = line.split("//", 1)[0]
		if not code.strip() or code.lstrip().startswith("#"):
			continue
		for match in QUOTED_PATH_RE.finditer(code):
			path = match.group(1)
			if _looks_like_dotted_python_path(path):
				refs.append(PathRef(file_path, lineno, path, "quoted"))
	return refs


def _collect_patch_paths() -> list[PathRef]:
	patches_txt = _get_phamos_app_path() / "patches.txt"
	if not patches_txt.exists():
		return []

	refs: list[PathRef] = []
	for lineno, raw in enumerate(patches_txt.read_text(encoding="utf-8").splitlines(), 1):
		line = raw.split("#", 1)[0].strip()
		if not line or line.startswith("["):
			continue
		if line.startswith("execute:"):
			continue
		module = line.split()[0]
		refs.append(PathRef(patches_txt, lineno, f"{module}.execute", "patch"))
	return refs


def _discover_import_refs() -> list[PathRef]:
	refs: list[PathRef] = []
	for file_path in _iter_phamos_files(".py"):
		try:
			refs.extend(_collect_phamos_imports(file_path))
		except SyntaxError as exc:
			refs.append(
				PathRef(file_path, exc.lineno or 1, _py_file_to_module(file_path), "syntax")
			)
	return refs


def _discover_dotted_path_refs() -> list[PathRef]:
	refs: list[PathRef] = []
	for file_path in _iter_phamos_files(".py"):
		try:
			refs.extend(_collect_string_paths_from_python(file_path))
		except SyntaxError:
			continue
	for file_path in _iter_phamos_files(".js", ".json"):
		refs.extend(_collect_quoted_paths_from_text(file_path))
	refs.extend(_collect_patch_paths())
	return refs


def _verify_path_ref(ref: PathRef) -> None:
	if ref.kind == "syntax":
		raise SyntaxError(f"cannot parse {_rel(ref.file)}")
	_assert_phamos_path_exists(ref.path)


def _format_failures(title: str, failures: list[tuple[PathRef, str]]) -> str:
	lines = [title]
	for ref, error in failures:
		lines.append(f"- {_rel(ref.file)}:{ref.lineno} -> {ref.path} ({ref.kind}): {error}")
	return "\n".join(lines)


def _is_remote_asset(value: str) -> bool:
	return value.startswith(("http://", "https://", "//"))


def _hook_file_candidates(value: str) -> list[Path]:
	app_path = _get_phamos_app_path()
	if value.startswith("/assets/phamos/"):
		return [app_path / "public" / value.removeprefix("/assets/phamos/")]
	if value.startswith("/") or _is_remote_asset(value):
		return []
	candidates = [app_path / value, app_path / "public" / "js" / value]
	if value.endswith(".bundle.js"):
		candidates.append(app_path / "public" / "js" / value)
	return candidates


def _iter_hook_file_values():
	import phamos.hooks as hooks_module

	for attr in HOOK_FILE_ATTRS:
		value = getattr(hooks_module, attr, None)
		if value is None:
			continue
		if isinstance(value, str):
			yield attr, value
		elif isinstance(value, (list, tuple)):
			for item in value:
				if isinstance(item, str):
					yield attr, item
		elif isinstance(value, dict):
			for item in value.values():
				if isinstance(item, str):
					yield attr, item
				elif isinstance(item, (list, tuple)):
					for nested in item:
						if isinstance(nested, str):
							yield attr, nested


class TestImportPaths(FrappeTestCase):
	def test_phamos_import_statements_resolve(self):
		"""Every ``import phamos...`` / ``from phamos... import`` must resolve."""
		failures: list[tuple[PathRef, str]] = []
		verified: set[str] = set()

		for ref in _discover_import_refs():
			if ref.path in verified and ref.kind != "syntax":
				continue
			verified.add(ref.path)
			try:
				_verify_path_ref(ref)
			except Exception as exc:
				failures.append((ref, f"{exc.__class__.__name__}: {exc}"))

		if failures:
			self.fail(
				_format_failures("Broken phamos import statements:", failures)
			)

	def test_dotted_python_paths_resolve(self):
		"""Hook / JS / patch strings like ``phamos.events....fn`` must exist."""
		refs = _discover_dotted_path_refs()
		self.assertIn(
			KNOWN_HOOK_PATH,
			{ref.path for ref in refs},
			"scanner missed a known hooks.py path",
		)

		failures: list[tuple[PathRef, str]] = []
		verified: set[str] = set()

		for ref in refs:
			if ref.path in verified:
				continue
			verified.add(ref.path)
			try:
				_verify_path_ref(ref)
			except Exception as exc:
				failures.append((ref, f"{exc.__class__.__name__}: {exc}"))

		if failures:
			self.fail(_format_failures("Broken phamos dotted paths:", failures))

	def test_hook_client_script_files_exist(self):
		"""doctype_js / app_include_js paths in hooks.py must point at real files."""
		missing: list[str] = []
		for attr, value in _iter_hook_file_values():
			if not value.endswith((".js", ".css")):
				continue
			if _is_remote_asset(value):
				continue
			candidates = _hook_file_candidates(value)
			if not candidates:
				continue
			if not any(path.exists() for path in candidates):
				checked = ", ".join(str(path) for path in candidates)
				missing.append(f"{attr}: {value} (looked in {checked})")

		if missing:
			self.fail("Missing files referenced from hooks.py:\n- " + "\n- ".join(missing))

	def test_all_python_modules_importable(self):
		"""Every phamos .py file must map to a ``phamos.*`` module path."""
		failures: list[str] = []
		verified: set[str] = set()

		for file_path in _iter_phamos_files(".py"):
			module_name = _py_file_to_module(file_path)
			if module_name in verified:
				continue
			verified.add(module_name)
			try:
				_assert_phamos_path_exists(module_name)
			except Exception as exc:
				failures.append(
					f"- {_rel(file_path)} -> {module_name}: {exc.__class__.__name__}: {exc}"
				)

		if failures:
			self.fail("phamos Python modules failed to import:\n" + "\n".join(failures))
