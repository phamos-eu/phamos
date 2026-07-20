from urllib.parse import quote

import frappe


def notify_lead_data_created_via_raven_dm(doc, method=None):
	"""Notify configured recipient via a personal Raven DM when Lead Data is created."""
	if "raven" not in frappe.get_installed_apps():
		return

	try:
		settings = frappe.get_single("Raven Bot Setting")
		raven_bot = settings.raven_bot
		recipient = settings.recipient_user

		if not raven_bot or not frappe.db.exists("Raven Bot", raven_bot):
			frappe.log_error(
				f"Raven Bot {raven_bot!r} configured in Raven Bot Setting was not found.",
				f"Lead Data Raven DM failed: {doc.name}",
			)
			return

		if not recipient:
			frappe.log_error(
				"No recipient_user configured in Raven Bot Setting.",
				f"Lead Data Raven DM failed: {doc.name}",
			)
			return

		bot = frappe.get_doc("Raven Bot", raven_bot)
		lead_name = quote(str(doc.name or ""), safe="")
		lead_title = (doc.get("organization_name") or doc.name or "").strip()
		lead_url = frappe.utils.get_url(f"/app/lead-data/{lead_name}")

		body = (settings.message_template or "").strip()
		body_lower = body.lower()
		options = [
			f"{row.option_key}) {row.option_label}"
			for row in settings.get("table_npdu", [])
			if (
				row.is_enabled
				and row.option_key
				and row.option_label
				and f"{row.option_key.strip().lower()})" not in body_lower
			)
		]

		text = f"New Lead Data created: **{frappe.as_unicode(lead_title)}**\n\n"
		email = (doc.get("card_email") or doc.get("email") or "").strip()
		contact_number = (doc.get("mobile_no") or doc.get("phone") or "").strip()
		if email:
			text += f"Email: {frappe.as_unicode(email)}\n\n"
		if contact_number:
			number_label = "Mobile" if doc.get("mobile_no") else "Phone"
			text += f"{number_label}: {frappe.as_unicode(contact_number)}\n\n"
		text += f"[Open Lead Data]({lead_url})"

		parent_message_id = bot.send_direct_message(
			user_id=recipient,
			text=text,
			link_doctype="Lead Data",
			link_document=doc.name,
			markdown=True,
		)

		# Raven threads use the parent message ID as their channel ID. Create the
		# thread immediately and post the configured actions as its first message.
		if body or options:
			from raven.api.threads import create_thread

			# Raven's thread header currently renders the standard owner instead of
			# the bot field. Align the parent owner with the Raven Bot identity and
			# create membership under the actual recipient, not the background
			# Administrator session.
			frappe.db.set_value(
				"Raven Message",
				parent_message_id,
				"owner",
				bot.raven_user,
				update_modified=False,
			)
			original_user = frappe.session.user
			try:
				frappe.set_user(recipient)
				thread = create_thread(parent_message_id)
			finally:
				frappe.set_user(original_user)
			thread_text = ""
			if body:
				thread_text += f"{body}\n\n"
			thread_text += "\n\n".join(options)
			bot.send_message(
				channel_id=thread["thread_id"],
				text=thread_text,
				markdown=True,
			)
	except Exception:
		frappe.log_error(
			frappe.get_traceback(),
			f"Lead Data Raven DM failed: {doc.name}",
		)
