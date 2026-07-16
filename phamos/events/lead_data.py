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
		if body:
			text += f"{body}\n\n"
		if options:
			text += "\n\n".join(options) + "\n\n"
		text += f"[Open Lead Data]({lead_url})"

		bot.send_direct_message(
			user_id=recipient,
			text=text,
			link_doctype="Lead Data",
			link_document=doc.name,
			markdown=True,
		)
	except Exception:
		frappe.log_error(
			frappe.get_traceback(),
			f"Lead Data Raven DM failed: {doc.name}",
		)
