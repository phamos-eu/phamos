from html import unescape

import frappe


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

	settings = frappe.get_single("Raven Bot Setting")
	if doc.owner != settings.recipient_user:
		return

	if not frappe.db.exists("Raven Message", doc.channel_id):
		return

	parent = frappe.get_doc("Raven Message", doc.channel_id)
	if parent.link_doctype != "Lead Data" or not parent.link_document:
		return

	option_key = (doc.content or "").strip().lower()
	lead_name = parent.link_document

	option_row = next(
		(
			row for row in settings.get("table_npdu", [])
			if (row.option_key or "").strip().lower() == option_key and row.is_enabled
		),
		None,
	)
	if not option_row:
		return

	if is_option_processed(lead_name, option_key):
		send_thread_reply(
			doc.channel_id,
			settings.raven_bot,
			f"⚠️ Option '{option_key}' has already been processed for this lead. No action was taken again.",
		)
		return

	run_action(option_row, lead_name, settings.recipient_user)
	reply_text = option_row.response_message or "✅ Done."

	mark_option_processed(lead_name, option_key)
	send_thread_reply(doc.channel_id, settings.raven_bot, reply_text)


def run_action(option_row, lead_name, recipient):
	"""Dispatch to the correct action based on the row's configured action_type."""
	if option_row.action_type == "Send Welcome Email":
		send_welcome_email(option_row, lead_name, recipient)
	elif option_row.action_type == "Suggest Appointment":
		suggest_appointment(lead_name)
	elif option_row.action_type == "Add to Newsletter":
		add_to_newsletter(lead_name)
	elif option_row.action_type == "All Actions":
		send_welcome_email(option_row, lead_name, recipient)
		suggest_appointment(lead_name)
		add_to_newsletter(lead_name)
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
	message_doc = frappe.get_doc({
		"doctype": "Raven Message",
		"channel_id": channel_id,
		"text": text,
		"content": text,
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
	)


def suggest_appointment(lead_name):
	pass  # not implemented yet


def add_to_newsletter(lead_name):
	pass  # not implemented yet
