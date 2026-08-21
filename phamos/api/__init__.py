# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""phamos.api package.

Submodules (scan, i_own_my_work, issue_raven) live under this package.
Legacy whitelisted helpers that used to live in ``phamos/api.py`` are
re-exported here so existing callers (``phamos.api.get_popup_doctypes``,
desk JS, hooks, tests) keep working alongside the new app APIs.
"""

from phamos.legacy_api import *  # noqa: F401, F403
from phamos import legacy_api as _legacy_api

# Preserve explicit attribute access for anything not covered by star-import
# (e.g. helpers that start with underscore if needed later).
__all__ = [name for name in dir(_legacy_api) if not name.startswith("__")]
