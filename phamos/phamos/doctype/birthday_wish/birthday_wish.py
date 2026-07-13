# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

from datetime import date

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, getdate, now_datetime, today

BIRTHDAY_LOOKAHEAD_DAYS = 30


class BirthdayWish(Document):
	def validate(self):
		self._validate_unique_wish_givers()

	def _validate_unique_wish_givers(self):
		seen = set()
		for row in self.birthday_wishes or []:
			if not row.wish_giver:
				continue
			if row.wish_giver in seen:
				frappe.throw(
					_("Duplicate birthday wish from {0}.").format(row.wish_giver)
				)
			seen.add(row.wish_giver)


def _get_current_employee():
	return frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")


def _celebration_date(date_of_birth, reference=None):
	"""Next occurrence of birthday on or after reference date."""
	ref = getdate(reference or today())
	dob = getdate(date_of_birth)
	candidate = date(ref.year, dob.month, dob.day)
	if candidate < ref:
		candidate = date(ref.year + 1, dob.month, dob.day)
	return candidate


def _days_until(celebration, reference):
	return (getdate(celebration) - getdate(reference)).days


def _get_or_create_birthday_wish(birthday_employee, celebration_date):
	docname = f"{birthday_employee}-{celebration_date}"
	if frappe.db.exists("Birthday Wish", docname):
		return frappe.get_doc("Birthday Wish", docname)

	due_date = add_days(celebration_date, -1)
	doc = frappe.get_doc(
		{
			"doctype": "Birthday Wish",
			"birthday_employee": birthday_employee,
			"birthday_date": celebration_date,
			"due_date": due_date,
			"status": "Collecting",
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


def _wish_already_submitted(parent_name, wish_giver):
	return frappe.db.exists(
		"Birthday Wishes",
		{
			"parent": parent_name,
			"parenttype": "Birthday Wish",
			"parentfield": "birthday_wishes",
			"wish_giver": wish_giver,
		},
	)


@frappe.whitelist()
def get_pending_birthday_wish_prompts():
	"""Colleagues with birthdays in the next 30 days the current user can still wish."""
	wish_giver = _get_current_employee()
	today_date = getdate(today())
	employees = frappe.get_all(
		"Employee",
		filters={"status": "Active", "date_of_birth": ["is", "set"]},
		fields=["name", "employee_name", "date_of_birth"],
		ignore_permissions=True,
	)

	pending = []
	for emp in employees:
		# Birthday person never sees their own wish prompt
		if wish_giver and emp.name == wish_giver:
			continue

		celebration = _celebration_date(emp.date_of_birth, today_date)
		days_until = _days_until(celebration, today_date)

		if days_until <= 0 or days_until > BIRTHDAY_LOOKAHEAD_DAYS:
			continue

		due_date = add_days(celebration, -1)
		if getdate(due_date) < today_date:
			continue

		try:
			parent = _get_or_create_birthday_wish(emp.name, celebration)
		except Exception:
			frappe.log_error(
				frappe.get_traceback(),
				"Birthday Wish: failed to load collection record",
			)
			continue

		if parent.status != "Collecting":
			continue

		if wish_giver and _wish_already_submitted(parent.name, wish_giver):
			continue

		pending.append(
			{
				"birthday_wish": parent.name,
				"birthday_employee": emp.name,
				"employee_name": emp.employee_name or emp.name,
				"birthday_date": str(celebration),
				"due_date": str(due_date),
				"days_until": days_until,
			}
		)

	pending.sort(key=lambda row: row["birthday_date"])
	return pending


@frappe.whitelist()
def save_birthday_wish_message(birthday_wish, message):
	"""Append or update the current user's wish on a Birthday Wish parent."""
	message = (message or "").strip()
	if not message:
		frappe.throw(_("Please enter a birthday message."))

	wish_giver = _get_current_employee()
	if not wish_giver:
		frappe.throw(_("Employee not found for the current user."))

	doc = frappe.get_doc("Birthday Wish", birthday_wish)
	today_date = getdate(today())

	if doc.status != "Collecting":
		frappe.throw(_("Birthday wishes are no longer being collected for this colleague."))

	if doc.due_date and getdate(doc.due_date) < today_date:
		frappe.throw(_("The deadline to submit birthday wishes has passed."))

	if doc.birthday_employee == wish_giver:
		frappe.throw(_("You cannot submit a birthday wish for yourself here."))

	wish_giver_name = frappe.db.get_value("Employee", wish_giver, "employee_name") or wish_giver

	existing_row = None
	for row in doc.birthday_wishes:
		if row.wish_giver == wish_giver:
			existing_row = row
			break

	if existing_row:
		existing_row.message = message
		existing_row.submitted_on = now_datetime()
		existing_row.wish_giver_name = wish_giver_name
	else:
		doc.append(
			"birthday_wishes",
			{
				"wish_giver": wish_giver,
				"wish_giver_name": wish_giver_name,
				"message": message,
				"submitted_on": now_datetime(),
			},
		)

	doc.save(ignore_permissions=True)
	return {"status": "ok", "birthday_wish": doc.name}


def _get_employee_raven_user(birthday_employee):
	"""Return (user_id, display_name) for Raven mention, or (None, name)."""
	display_name = (
		frappe.db.get_value("Employee", birthday_employee, "employee_name")
		or birthday_employee
	)
	user_id = frappe.db.get_value("Employee", birthday_employee, "user_id")
	if user_id and frappe.db.exists("Raven User", user_id):
		return user_id, display_name
	return None, display_name


def _build_user_mention_html(user_id, label):
	return (
		f'<span data-type="userMention" class="mention" '
		f'data-id="{frappe.utils.escape_html(user_id)}" '
		f'data-label="{frappe.utils.escape_html(label)}">'
		f"@{frappe.utils.escape_html(label)}</span>"
	)


def _compose_birthday_message_body(doc):
	"""Return plain-text/markdown body for the birthday post (mention added separately)."""
	wishes = []
	for row in doc.birthday_wishes or []:
		message = (row.message or "").strip()
		if not message:
			continue
		name = row.wish_giver_name or row.wish_giver
		wishes.append({"name": name, "message": message})

	employee_name = doc.employee_name or doc.birthday_employee

	if not wishes:
		return _(
			"Happy Birthday, {0}! 🎉 Wishing you a wonderful day from the whole phamos team!"
		).format(employee_name)

	from phamos.phamos.doctype.accounting_receipt.mistral_pdf import _get_phamos_settings
	from phamos.phamos.hr.interview_summary import _call_mistral_chat

	settings = _get_phamos_settings()
	if settings:
		wish_lines = "\n".join(
			f'- {item["name"]}: "{item["message"]}"' for item in wishes
		)
		prompt = f"""You are writing a warm team birthday message for a workplace chat channel.

Birthday person: {employee_name}

Messages collected from colleagues:
{wish_lines}

Write one cohesive birthday message (max 200 words) that:
- Opens with an enthusiastic happy birthday to {employee_name}
- Weaves in the spirit of the colleagues' messages without quoting everyone verbatim
- Keeps a friendly, professional phamos team tone
- Uses markdown for emphasis where helpful
- Does NOT include @mentions (those are added separately)
- Does NOT invent wishes that were not collected

Return only the message body."""

		try:
			composed = _call_mistral_chat(settings, prompt)
			if composed:
				return composed.strip()
		except Exception:
			frappe.log_error(
				frappe.get_traceback(),
				"Birthday Wish: Mistral compose failed",
			)

	lines = [
		_("Happy Birthday, {0}! 🎉").format(employee_name),
		"",
		_("Your colleagues shared these wishes:"),
		"",
	]
	for item in wishes:
		lines.append(f"**{item['name']}**: {item['message']}")
	return "\n".join(lines)


def _build_birthday_raven_html(doc, body=None):
	user_id, display_name = _get_employee_raven_user(doc.birthday_employee)
	body = body if body is not None else _compose_birthday_message_body(doc)
	body_html = frappe.utils.markdown(body)

	if user_id:
		mention = _build_user_mention_html(user_id, display_name)
		return f"<p>{mention}</p>{body_html}"

	return body_html


def get_birthday_wishes_to_post(today_date=None):
	today_date = getdate(today_date or today())
	return frappe.get_all(
		"Birthday Wish",
		filters={
			"birthday_date": today_date,
			"status": ["!=", "Posted to Raven"],
		},
		pluck="name",
	)


def get_todays_raven_daily_thread_id(today_date=None):
	"""Return the parent Raven Message name for today's daily thread, if it exists."""
	from phamos.custom_scripts.custom_python.raven_daily_thread import _get_settings

	settings = _get_settings()
	if not settings.raven_channel:
		return None

	today_date = getdate(today_date or today())
	today_compact = today_date.strftime("%Y%m%d")

	candidates = frappe.get_all(
		"Raven Message",
		filters={
			"channel_id": settings.raven_channel,
			"is_thread": 1,
			"text": ["like", f"%{today_compact} - Daily%"],
		},
		fields=["name", "creation"],
		order_by="creation desc",
		limit=1,
	)
	if candidates:
		return candidates[0].name

	# Fallback: most recent thread root in today's configured channel
	start = f"{today_date} 00:00:00"
	end = f"{today_date} 23:59:59"
	fallback = frappe.get_all(
		"Raven Message",
		filters={
			"channel_id": settings.raven_channel,
			"is_thread": 1,
			"creation": ["between", [start, end]],
		},
		fields=["name"],
		order_by="creation desc",
		limit=1,
	)
	return fallback[0].name if fallback else None


def post_birthday_wishes_to_raven_thread(thread_channel_id, raven_bot, today_date=None):
	"""Post collected birthday wishes as replies in the daily Raven thread."""
	today_date = getdate(today_date or today())
	birthday_wish_names = get_birthday_wishes_to_post(today_date)

	if not birthday_wish_names:
		return []

	from phamos.custom_scripts.custom_python.raven_daily_thread import _bot_send_message

	bot = frappe.get_doc("Raven Bot", raven_bot)
	posted = []

	for name in birthday_wish_names:
		doc = frappe.get_doc("Birthday Wish", name)
		try:
			body = _compose_birthday_message_body(doc)
			html = _build_birthday_raven_html(doc, body)
			message_id = _bot_send_message(bot, thread_channel_id, html)
			doc.db_set(
				{
					"status": "Posted to Raven",
					"raven_message_id": message_id,
					"ai_composed_message": body,
				},
				update_modified=True,
			)
			posted.append(name)
		except Exception:
			frappe.log_error(
				frappe.get_traceback(),
				f"Birthday Wish: failed to post to Raven ({name})",
			)

	if posted:
		frappe.db.commit()

	return posted


@frappe.whitelist()
def test_post_birthday_wish_to_raven(birthday_wish, thread_channel_id=None):
	"""Manually post one Birthday Wish to Raven (for testing)."""
	from phamos.custom_scripts.custom_python.raven_daily_thread import (
		_bot_send_message,
		_get_settings,
		_validate_raven_installed,
	)

	_validate_raven_installed()
	settings = _get_settings()

	if not settings.raven_bot:
		frappe.throw(_("Raven Bot is not configured in phamos Settings."))

	doc = frappe.get_doc("Birthday Wish", birthday_wish)
	if doc.status == "Posted to Raven":
		frappe.throw(_("This birthday wish was already posted to Raven."))

	if not thread_channel_id:
		thread_channel_id = get_todays_raven_daily_thread_id()
	if not thread_channel_id:
		frappe.throw(
			_(
				"No daily Raven thread found for today. Create one first (phamos Settings → Test Raven Thread), or pass thread_channel_id."
			)
		)

	bot = frappe.get_doc("Raven Bot", settings.raven_bot)
	body = _compose_birthday_message_body(doc)
	html = _build_birthday_raven_html(doc, body)
	message_id = _bot_send_message(bot, thread_channel_id, html)
	doc.db_set(
		{
			"status": "Posted to Raven",
			"raven_message_id": message_id,
			"ai_composed_message": body,
		},
		update_modified=True,
	)
	frappe.db.commit()
	return {"status": "ok", "raven_message_id": message_id, "birthday_wish": doc.name}
