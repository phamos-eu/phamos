# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""An idea of the Personal Cockpit (phamos/phamos#1771). Logic lives in phamos.api.personal_ideas."""

import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime, strip_html

from phamos.api.personal_todos import BLOCK_END
from phamos.cockpits.defaults import IDEA_STAGES, IDEA_SUMMARY_LENGTH, IDEA_TITLE_LENGTH


def excerpt(html, length=IDEA_SUMMARY_LENGTH):
	"""Plain text of an HTML body, whitespace collapsed, cut at `length` with an ellipsis."""
	text = re.sub(r"\s+", " ", strip_html(BLOCK_END.sub(" ", html or ""))).strip()
	text = text.replace("&nbsp;", " ").strip()
	return text if len(text) <= length else text[: length - 1].rstrip() + "…"


class Idea(Document):
	def validate(self):
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

	def on_trash(self):
		frappe.db.set_value("Idea", {"spawned_from": self.name}, "spawned_from", None, update_modified=False)
		for name in frappe.get_all("Idea Writing Session", {"idea": self.name}, pluck="name"):
			frappe.delete_doc("Idea Writing Session", name, ignore_permissions=True, force=True)
