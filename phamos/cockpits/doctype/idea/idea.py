# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""An idea of the Personal Cockpit (phamos/phamos#1771). Logic lives in phamos.api.personal_ideas."""

import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime, strip_html

from phamos.api.personal_todos import BLOCK_END
from phamos.cockpits.defaults import (
	IDEA_STAGES,
	IDEA_SUMMARY_LENGTH,
	IDEA_TITLE_LENGTH,
	IDEA_VOTE_BLOCKED_STAGES,
	IDEA_VOTE_OPEN,
)


# Fields an employee may not set from Desk, with their value on a new idea (#1951).
DESK_PROTECTED_FIELDS = {"vote_count": 0, "handed_in_on": None, "imported_from": None, "team": None}


def excerpt(html, length=IDEA_SUMMARY_LENGTH):
	"""Plain text of an HTML body, whitespace collapsed, cut at `length` with an ellipsis."""
	text = re.sub(r"\s+", " ", strip_html(BLOCK_END.sub(" ", html or ""))).strip()
	text = text.replace("&nbsp;", " ").strip()
	return text if len(text) <= length else text[: length - 1].rstrip() + "…"


class Idea(Document):
	def validate(self):
		self._validate_user()
		self.title = (self.title or "").strip()[:IDEA_TITLE_LENGTH] or _("Untitled idea")
		self.stage = self.stage or "Seed"
		if self.stage not in IDEA_STAGES:
			frappe.throw(_("Unknown stage: {0}").format(self.stage))
		self.summary = excerpt(self.content)
		if self.spawned_from:
			if self.spawned_from == self.name:
				frappe.throw(_("An idea cannot come from itself."))
			if frappe.db.get_value("Idea", self.spawned_from, "user") != self.user:
				frappe.throw(_("This idea is not yours."), frappe.PermissionError)
		if self.stage == "Harvest":
			self.harvested_on = self.harvested_on or now_datetime()
		else:
			self.harvested_on = None
		self._validate_vote()

	def _validate_user(self):
		"""Employees create and edit their own ideas in Desk (#1951): the idea is the creator's.
		The cockpit API (ignore_permissions) and System Managers (Idea Import) set `user` themselves."""
		me = frappe.session.user
		self.user = self.user or me
		if self.flags.ignore_permissions or me == "Administrator" or "System Manager" in frappe.get_roles(me):
			return
		before = self.get_doc_before_save()
		if self.user != me or (before and before.user != me):
			frappe.throw(_("This idea is not yours."), frappe.PermissionError)
		# Read-only only stops the form, not the REST API: the owner must not set their own vote
		# count or hand-in time (the vote ranking), nor the import key (Idea Import's dedupe).
		for field, new_value in DESK_PROTECTED_FIELDS.items():
			self.set(field, before.get(field) if before else new_value)

	def _validate_vote(self):
		"""Hand in for vote (#1842): composting withdraws; the hand-in time follows the status."""
		if self.stage in IDEA_VOTE_BLOCKED_STAGES:
			self.vote_status = ""
		if self.vote_status and self.vote_status != IDEA_VOTE_OPEN:
			frappe.throw(_("Unknown vote status: {0}").format(self.vote_status))
		if self.vote_status:
			self.handed_in_on = self.handed_in_on or now_datetime()
		else:
			self.vote_status = ""
			self.handed_in_on = None
			# a private idea is shared with nobody (#1980)
			self.team = None

	def on_update(self):
		before = self.get_doc_before_save()
		if not before or (before.vote_status or "") == (self.vote_status or ""):
			return
		# Withdrawn (by hand or by composting): the votes of this round go.
		if not self.vote_status:
			_delete_votes(self.name)
			if self.vote_count:
				self.db_set("vote_count", 0, update_modified=False)
		# Its Raven chat is archived while the idea is private, and back when handed in again.
		from phamos.api import issue_chat

		issue_chat.on_idea_vote_change(self)

	def on_trash(self):
		_delete_votes(self.name)
		frappe.db.set_value("Idea", {"spawned_from": self.name}, "spawned_from", None, update_modified=False)
		for name in frappe.get_all("Idea Writing Session", {"idea": self.name}, pluck="name"):
			frappe.delete_doc("Idea Writing Session", name, ignore_permissions=True, force=True)


def _delete_votes(idea):
	frappe.db.delete("Idea Vote", {"idea": idea})
