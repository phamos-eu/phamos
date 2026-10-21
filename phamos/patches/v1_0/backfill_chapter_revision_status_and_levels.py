"""Fill Implementation Chapter Revision status and levels for revisions created before
those fields existed.

A Chapter's current revision mirrors the Chapter's live status and levels, so it copies
them from the Chapter. Every older revision was created by Set as Planned, so it gets
Planned; its levels at that time are unknown and stay empty.
"""

import frappe
from frappe.query_builder.functions import IfNull


def execute():
	revision = frappe.qb.DocType("Implementation Chapter Revision")
	chapter = frappe.qb.DocType("Implementation Chapter")

	(
		frappe.qb.update(revision)
		.join(chapter)
		.on(chapter.current_revision == revision.name)
		.set(revision.status, chapter.status)
		.set(revision.current_level, chapter.current_level)
		.set(revision.target_level, chapter.target_level)
	).run()

	# Sites that already migrated the field got its old "Draft" default; no revision is ever Draft.
	(
		frappe.qb.update(revision)
		.set(revision.status, "Planned")
		.where(IfNull(revision.status, "").isin(["", "Draft"]))
	).run()
