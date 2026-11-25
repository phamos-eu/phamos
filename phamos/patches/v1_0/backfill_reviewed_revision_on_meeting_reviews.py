
import frappe


def execute():
	frappe.db.sql(
		"""
		UPDATE `tabStakeholder Meeting Chapter Review` review
		INNER JOIN `tabStakeholder Meeting` meeting ON meeting.name = review.parent
		SET review.current_revision = (
			SELECT revision.name
			FROM `tabImplementation Chapter Revision` revision
			WHERE revision.implementation_chapter = review.chapter
				AND revision.creation <= meeting.modified
			ORDER BY revision.revision_number DESC
			LIMIT 1
		)
		WHERE review.parenttype = 'Stakeholder Meeting'
			AND meeting.docstatus = 1
			AND IFNULL(review.current_revision, '') = ''
		"""
	)
