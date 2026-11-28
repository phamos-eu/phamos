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

	current_revisions = (
		frappe.qb.from_(revision)
		.join(chapter)
		.on(chapter.current_revision == revision.name)
		.select(revision.name, chapter.status, chapter.current_level, chapter.target_level)
	).run(as_dict=True)

	for row in current_revisions:
		(
			frappe.qb.update(revision)
			.set(revision.status, row.status)
			.set(revision.current_level, row.current_level)
			.set(revision.target_level, row.target_level)
			.where(revision.name == row.name)
		).run()

	# Sites that already migrated the field got its old "Draft" default; no revision is ever Draft.
	(
		frappe.qb.update(revision)
		.set(revision.status, "Planned")
		.where(IfNull(revision.status, "").isin(["", "Draft"]))
	).run()
