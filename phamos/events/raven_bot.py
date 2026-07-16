from html import unescape
import json

import frappe
from frappe.utils import strip_html


APPOINTMENT_DURATIONS = {
	"a": 15,
	"15": 15,
	"15min": 15,
	"15mins": 15,
	"b": 30,
	"30": 30,
	"30min": 30,
	"30mins": 30,
	"c": 60,
	"60": 60,
	"60min": 60,
	"60mins": 60,
}


def prepare_email_body(value):
	message = (value or "").strip()
	prefix = '<div class="ql-editor read-mode"><p>'
	suffix = "</p></div>"
	if message.startswith(prefix) and message.endswith(suffix):
		message = message[len(prefix):-len(suffix)]
	if "&lt;" in message or "&gt;" in message:
		message = unescape(message)
	return message


def handle_lead_option_reply(doc, method=None):
	if not doc.content:
		return
	# Never process the bot's own thread replies as user selections. In the
	# appointment flow a pending duration exists before the bot sends its prompt;
	# without this guard that prompt recursively triggers another bot reply.
	if doc.is_bot_message:
		return

	settings = frappe.get_single("Raven Bot Setting")
	if doc.owner != settings.recipient_user:
		return

	if not frappe.db.exists("Raven Message", doc.channel_id):
		return

	parent = frappe.get_doc("Raven Message", doc.channel_id)
	if parent.link_doctype != "Lead Data" or not parent.link_document:
		return

	option_key = strip_html(doc.content or "").strip().lower().replace(" ", "")
	lead_name = parent.link_document

	pending_slots = get_pending_appointment_slots(lead_name, doc.channel_id)
	if pending_slots:
		if option_key not in {"1", "2", "3"}:
			send_thread_reply(
				doc.channel_id,
				settings.raven_bot,
				"Please select one of the available slots:\n1) First slot\n2) Second slot\n3) Third slot",
			)
			return

		slot_index = int(option_key) - 1
		if slot_index >= len(pending_slots):
			send_thread_reply(
				doc.channel_id,
				settings.raven_bot,
				f"Slot {option_key} is not available. Please select a listed slot number.",
			)
			return

		try:
			event = book_appointment_slot(
				lead_name,
				settings.recipient_user,
				pending_slots[slot_index],
			)
		except Exception:
			frappe.log_error(
				title="Raven appointment booking failed",
				message=frappe.get_traceback(),
			)
			send_thread_reply(
				doc.channel_id,
				settings.raven_bot,
				"The slot could not be booked in the recipient user's calendar. "
				"Please check the DAV configuration and try the slot number again.",
			)
			return

		mark_appointment_slot_booked(lead_name, doc.channel_id, event.name)
		send_thread_reply(
			doc.channel_id,
			settings.raven_bot,
			f"✅ Meeting booked successfully.\n"
			f"Slot: {pending_slots[slot_index]['label']}\n"
			f"Event: {event.name}",
		)
		return

	# Appointment duration is a second step in the same Raven thread. Handle it
	# before matching the main a/b/c/d options, because those keys are reused by
	# the duration choices.
	if is_appointment_duration_pending(lead_name, doc.channel_id):
		duration = APPOINTMENT_DURATIONS.get(option_key)
		if not duration:
			send_thread_reply(
				doc.channel_id,
				settings.raven_bot,
				"Please choose a meeting duration:\n"
				"a) 15 minutes\n"
				"b) 30 minutes\n"
				"c) 60 minutes",
			)
			return

		reply_text, lookup_succeeded, slots = available_slot_message(
			settings.recipient_user,
			duration,
		)
		if lookup_succeeded:
			mark_appointment_duration_completed(lead_name, doc.channel_id)
			if slots:
				store_appointment_slots(lead_name, doc.channel_id, slots)
		send_thread_reply(doc.channel_id, settings.raven_bot, reply_text)
		return

	option_row = next(
		(
			row for row in settings.get("table_npdu", [])
			if (row.option_key or "").strip().lower() == option_key and row.is_enabled
		),
		None,
	)
	if not option_row:
		return

	if (
		is_option_processed(lead_name, option_key)
		and option_row.action_type != "Suggest Appointment"
	):
		send_thread_reply(
			doc.channel_id,
			settings.raven_bot,
			f"⚠️ Option '{option_key}' has already been processed for this lead. No action was taken again.",
		)
		return

	action_reply = run_action(
		option_row,
		lead_name,
		settings.recipient_user,
		doc.channel_id,
	)
	reply_text = action_reply or option_row.response_message or "✅ Done."

	mark_option_processed(lead_name, option_key)
	send_thread_reply(doc.channel_id, settings.raven_bot, reply_text)


def run_action(option_row, lead_name, recipient, channel_id):
	"""Dispatch to the correct action based on the row's configured action_type."""
	if option_row.action_type == "Send Welcome Email":
		send_welcome_email(option_row, lead_name, recipient)
	elif option_row.action_type == "Suggest Appointment":
		return suggest_appointment(lead_name, recipient, channel_id)
	elif option_row.action_type == "Add to Newsletter":
		add_to_newsletter(lead_name)
	elif option_row.action_type == "All Actions":
		send_welcome_email(option_row, lead_name, recipient)
		appointment_reply = suggest_appointment(lead_name, recipient, channel_id)
		add_to_newsletter(lead_name)
		return appointment_reply
	# "No Action" -> nothing to do


def is_option_processed(lead_name, option_key):
	return frappe.db.exists(
		"Comment",
		{
			"reference_doctype": "Lead Data",
			"reference_name": lead_name,
			"content": f"raven_bot_option_processed:{option_key}",
		},
	)


def mark_option_processed(lead_name, option_key):
	frappe.get_doc({
		"doctype": "Comment",
		"comment_type": "Info",
		"reference_doctype": "Lead Data",
		"reference_name": lead_name,
		"content": f"raven_bot_option_processed:{option_key}",
	}).insert(ignore_permissions=True)


def send_thread_reply(channel_id, bot_name, text):
	# Raven renders message.text as Tiptap HTML. Separate paragraphs are retained
	# by its sanitizer/renderer, while plain newlines and standalone <br> tags are
	# flattened in the thread UI.
	lines = (text or "").splitlines() or [""]
	rendered_text = "".join(
		f"<p>{frappe.utils.escape_html(line) or '<br>'}</p>"
		for line in lines
	)
	message_doc = frappe.get_doc({
		"doctype": "Raven Message",
		"channel_id": channel_id,
		"text": rendered_text,
		"content": rendered_text,
		"message_type": "Text",
		"is_bot_message": 1,
		"bot": bot_name,
	})
	message_doc.insert(ignore_permissions=True)
	frappe.db.commit()

	frappe.publish_realtime(
		"new_message",
		{"channel_id": channel_id, "message": message_doc.as_dict()},
		doctype="Raven Channel",
		docname=channel_id,
	)
	return message_doc


def send_welcome_email(option_row, lead_name, recipient):
	if not recipient:
		frappe.throw("Please select a Recipient User in Raven Bot Setting.")

	subject = option_row.email_subject or "Welcome to Phamos"
	message = prepare_email_body(option_row.email_body)

	attachments = []
	if option_row.email_attachment:
		file_doc = frappe.get_doc("File", {"file_url": option_row.email_attachment})
		attachments.append({
			"fname": file_doc.file_name,
			"fcontent": file_doc.get_content(),
		})

	frappe.sendmail(
		recipients=[recipient],
		subject=subject,
		message=message,
		attachments=attachments,
		reference_doctype="Lead Data",
		reference_name=lead_name,
		now=True,
	)


def _appointment_state_content(state, channel_id):
	return f"raven_bot_appointment_{state}:{channel_id}"


def is_appointment_duration_pending(lead_name, channel_id):
	states = frappe.get_all(
		"Comment",
		filters={
			"reference_doctype": "Lead Data",
			"reference_name": lead_name,
			"content": ["in", [
				_appointment_state_content("pending", channel_id),
				_appointment_state_content("completed", channel_id),
			]],
		},
		fields=["content"],
		order_by="creation desc",
		limit=1,
	)
	return bool(
		states
		and states[0].content == _appointment_state_content("pending", channel_id)
	)


def _add_appointment_state(lead_name, channel_id, state):
	frappe.get_doc({
		"doctype": "Comment",
		"comment_type": "Info",
		"reference_doctype": "Lead Data",
		"reference_name": lead_name,
		"content": _appointment_state_content(state, channel_id),
	}).insert(ignore_permissions=True)


def mark_appointment_duration_completed(lead_name, channel_id):
	_add_appointment_state(lead_name, channel_id, "completed")


def _appointment_slots_prefix(channel_id):
	return f"raven_bot_appointment_slots:{channel_id}:"


def _appointment_booked_content(channel_id):
	return f"raven_bot_appointment_booked:{channel_id}"


def store_appointment_slots(lead_name, channel_id, slots):
	frappe.get_doc({
		"doctype": "Comment",
		"comment_type": "Info",
		"reference_doctype": "Lead Data",
		"reference_name": lead_name,
		"content": _appointment_slots_prefix(channel_id) + json.dumps(slots),
	}).insert(ignore_permissions=True)


def get_pending_appointment_slots(lead_name, channel_id):
	if frappe.db.exists(
		"Comment",
		{
			"reference_doctype": "Lead Data",
			"reference_name": lead_name,
			"content": ["like", _appointment_booked_content(channel_id) + "%"],
		},
	):
		return []

	rows = frappe.get_all(
		"Comment",
		filters={
			"reference_doctype": "Lead Data",
			"reference_name": lead_name,
			"content": ["like", _appointment_slots_prefix(channel_id) + "%"],
		},
		fields=["content"],
		order_by="creation desc",
		limit=1,
	)
	if not rows:
		return []

	try:
		return json.loads(rows[0].content[len(_appointment_slots_prefix(channel_id)):])
	except (TypeError, ValueError):
		return []


def mark_appointment_slot_booked(lead_name, channel_id, event_name):
	frappe.get_doc({
		"doctype": "Comment",
		"comment_type": "Info",
		"reference_doctype": "Lead Data",
		"reference_name": lead_name,
		"content": f"{_appointment_booked_content(channel_id)}:{event_name}",
	}).insert(ignore_permissions=True)


def book_appointment_slot(lead_name, recipient, slot):
	if not recipient:
		frappe.throw("Please select a Recipient User in Raven Bot Setting.")

	lead_title = (
		frappe.db.get_value("Lead Data", lead_name, "organization_name")
		or lead_name
	)
	event = frappe.get_doc({
		"doctype": "Event",
		"subject": f"Appointment with {lead_title}",
		"event_type": "Private",
		"starts_on": slot["start_local"],
		"ends_on": slot["end_local"],
		"description": f"Appointment booked from Raven for Lead Data {lead_name}",
		"owner": recipient,
	})
	event.insert(ignore_permissions=True)
	event.reload()
	if not event.get("custom_mailcow_synched"):
		frappe.throw("The Event was not synchronized to Mailcow.")
	return event


def suggest_appointment(lead_name, recipient, channel_id):
	if not recipient:
		frappe.throw("Please select a Recipient User in Raven Bot Setting.")

	if not is_appointment_duration_pending(lead_name, channel_id):
		_add_appointment_state(lead_name, channel_id, "pending")

	return (
		"How long should the meeting be?\n"
		"a) 15 minutes\n"
		"b) 30 minutes\n"
		"c) 60 minutes"
	)


def available_slot_message(recipient, duration_minutes):
	from phamos.mailcow_integration.availability.next_free_slot import (
		next_three_free_slots_for_user,
	)

	try:
		slots = next_three_free_slots_for_user(
			recipient,
			duration_minutes=duration_minutes,
		)
	except Exception:
		frappe.log_error(
			title="Raven appointment calendar lookup failed",
			message=frappe.get_traceback(),
		)
		return (
			"I could not read the recipient user's Mailcow calendar. Please check "
			"Mailcow Settings and the user's DAV password, then reply with the "
			"duration again.",
			False,
			[],
		)

	if not slots:
		return (
			f"No {duration_minutes}-minute slots were found in the next 14 days "
			"on the recipient user's calendar.",
			True,
			[],
		)

	lines = [f"Available {duration_minutes}-minute slots:"]
	for index, slot in enumerate(slots, start=1):
		lines.append(f"{index}) {slot['label']}")
	lines.append("Reply with 1, 2, or 3 to book a slot.")
	return "\n".join(lines), True, slots


def add_to_newsletter(lead_name):
	pass  # not implemented yet
