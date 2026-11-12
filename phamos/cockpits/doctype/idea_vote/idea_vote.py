# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""One user's upvote on an idea handed in for a vote (phamos/phamos#1842).

Logic lives in phamos.api.personal_ideas; this guards the rules for any other way in.
"""

import frappe
from frappe import _
from frappe.model.document import Document

from phamos.cockpits.defaults import IDEA_VOTE_OPEN


class IdeaVote(Document):
	def validate(self):
		idea = frappe.db.get_value("Idea", self.idea, ["user", "vote_status"], as_dict=True)
		if not idea:
			frappe.throw(_("Idea {0} not found").format(self.idea), frappe.DoesNotExistError)
		if idea.vote_status != IDEA_VOTE_OPEN:
			frappe.throw(_("This idea is not open for a vote."))
		if idea.user == self.user:
			frappe.throw(_("You cannot vote for your own idea."))


def on_doctype_update():
	# One vote per user and idea, also when two requests race.
	frappe.db.add_unique("Idea Vote", ["idea", "user"], constraint_name="unique_idea_user")
