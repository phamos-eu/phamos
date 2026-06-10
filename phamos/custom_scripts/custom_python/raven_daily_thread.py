import random
from datetime import datetime

import frappe

from phamos.custom_scripts.custom_python.mattermost_daily_thread import get_thought_of_the_day

PHAMOS_EMOJIS = ["🌅", "🌞", "🌿", "🌼", "🌈", "💫", "🌻", "🌟"]
REPLY_EMOJIS = [
	"😊", "🎉", "👍", "🚀", "🔥", "😎", "🌟", "💪", "💥", "🎈",
	"😃", "😍", "🥳", "🌈", "💖", "✨", "💯", "💫", "🌻", "🦄",
	"🙌", "🥰", "💚", "💙", "🧡", "💛", "🌸", "🎊", "🥂", "🎶",
]


def _get_settings():
	return frappe.get_single("phamos Settings")


def _validate_raven_installed():
	if "raven" not in frappe.get_installed_apps():
		frappe.throw("Raven app is not installed on this site.")


def _get_daily_image_file_url(settings, quote):
	if settings.daily_image_folder:
		return settings.daily_image_folder

	from phamos.custom_scripts.custom_python.mistral_daily_image import (
		generate_daily_image_from_quote,
	)

	return generate_daily_image_from_quote(quote)


@frappe.whitelist()
def create_raven_thread():
	"""Create the daily good-morning thread in Raven (weekday scheduler)."""
	_validate_raven_installed()

	settings = _get_settings()
	if not settings.enable_raven_daily_thread:
		return

	today_date = frappe.utils.today()
	last_date = settings.last_daily_thread_creation_date_raven
	if last_date and str(last_date) == today_date:
		frappe.logger("phamos").info(
			"Raven daily thread already created for today: %s", today_date
		)
		return

	if not settings.raven_bot:
		frappe.throw("Raven Bot is not configured in phamos Settings.")
	if not settings.raven_channel:
		frappe.throw("Raven Channel is not configured in phamos Settings.")

	_create_raven_thread(settings, today_date)


def _create_raven_thread(settings, today_date):
	from raven.api.threads import create_thread

	thought_of_the_day = get_thought_of_the_day()
	phamos_emoji = random.choice(PHAMOS_EMOJIS)
	reply_emoji = random.choice(REPLY_EMOJIS)
	today_compact = datetime.now().strftime("%Y%m%d")

	bot = frappe.get_doc("Raven Bot", settings.raven_bot)
	channel_id = settings.raven_channel
	bot.add_to_channel(channel_id)

	parent_text = f"{today_compact} - Daily {phamos_emoji}"
	parent_message_id = bot.send_message(channel_id, parent_text)

	create_thread(parent_message_id)

	reply_message = (
		f"Good Morning 'phamos' {phamos_emoji} 🙏\n> {thought_of_the_day} {reply_emoji}"
	)
	bot.send_message(parent_message_id, reply_message, markdown=True)

	if settings.enable_daily_image:
		try:
			image_file = _get_daily_image_file_url(settings, thought_of_the_day)
			bot.send_message(parent_message_id, text="", file=image_file)
		except Exception:
			frappe.log_error(
				frappe.get_traceback(),
				"Raven Daily Thread: failed to post daily image",
			)

	frappe.db.set_single_value(
		"phamos Settings",
		"last_daily_thread_creation_date_raven",
		today_date,
	)
	frappe.db.commit()

@frappe.whitelist()
def test_raven_thread():
	"""Manually trigger the Raven daily thread (ignores last-run date)."""
	_validate_raven_installed()
	settings = _get_settings()

	if not settings.raven_bot:
		frappe.throw("Raven Bot is not configured in phamos Settings.")
	if not settings.raven_channel:
		frappe.throw("Raven Channel is not configured in phamos Settings.")

	today_date = frappe.utils.today()
	_create_raven_thread(settings, today_date)
	return {"status": "ok", "date": today_date}
