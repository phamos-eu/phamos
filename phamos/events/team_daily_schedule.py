from __future__ import annotations

"""Backward-compatible re-exports.

Team Daily Schedule sync now lives in
``phamos.mailcow_integration.schedule_sync``. Hooks should call that module
directly; these aliases keep older imports working.
"""

from phamos.mailcow_integration.schedule_sync import (  # noqa: F401
	SCHEDULE_PARENTS,
	SCHEDULE_ROW_DOCTYPE,
	cleanup_events_on_parent_trash,
	get_schedule_table_field,
	sync_events_from_parent,
)

# Historical constant used by older callers
SCHEDULE_TABLE_FIELD = "custom_team_daily_schedule"
