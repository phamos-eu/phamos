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


def _set_bot_message_owner(message_name, bot):
	"""Raven thread header reads owner, not is_bot_message — show the bot, not session user."""
	if bot.raven_user:
		frappe.db.set_value(
			"Raven Message",
			message_name,
			"owner",
			bot.raven_user,
			update_modified=False,
		)


def _bot_send_message(bot, channel_id, text="", **kwargs):
	message_id = bot.send_message(channel_id, text, **kwargs)
	_set_bot_message_owner(message_id, bot)
	return message_id


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


def _post_daily_image(settings, raven_bot, parent_message_id, quote):
	image_file = _get_daily_image_file_url(settings, quote)
	bot = frappe.get_doc("Raven Bot", raven_bot)
	_bot_send_message(bot, parent_message_id, text="", file=image_file)


def _enqueue_daily_image(settings, parent_message_id, quote, today_date=None):
	"""Mistral image gen can exceed the default worker timeout — run on long queue."""
	frappe.enqueue(
		"phamos.custom_scripts.custom_python.raven_daily_thread.post_raven_daily_image",
		queue="long",
		timeout=900,
		enqueue_after_commit=True,
		raven_bot=settings.raven_bot,
		parent_message_id=parent_message_id,
		quote=quote,
		daily_image_folder=settings.daily_image_folder,
		today_date=today_date,
		job_id=f"raven_daily_image_{frappe.utils.today()}",
		deduplicate=True,
	)


def post_raven_daily_image(
	raven_bot, parent_message_id, quote, daily_image_folder=None, today_date=None
):
	"""Background job: generate (or use fixed) image and post to the daily thread."""
	try:
		settings = frappe._dict(
			raven_bot=raven_bot,
			daily_image_folder=daily_image_folder,
		)
		_post_daily_image(settings, raven_bot, parent_message_id, quote)
	except Exception:
		frappe.log_error(
			frappe.get_traceback(),
			"Raven Daily Thread: failed to post daily image",
		)

	if today_date:
		_post_birthday_wishes_after_thread(parent_message_id, raven_bot, today_date)


def _post_birthday_wishes_after_thread(thread_channel_id, raven_bot, today_date):
	from phamos.phamos.doctype.birthday_wish.birthday_wish import (
		post_birthday_wishes_to_raven_thread,
	)

	try:
		posted = post_birthday_wishes_to_raven_thread(
			thread_channel_id, raven_bot, today_date
		)
		if posted:
			frappe.logger("phamos").info(
				"Posted birthday wishes to Raven thread for: %s", ", ".join(posted)
			)
	except Exception:
		frappe.log_error(
			frappe.get_traceback(),
			"Raven Daily Thread: failed to post birthday wishes",
		)


def _create_raven_thread(settings, today_date, post_image_sync=False):
	from raven.api.threads import create_thread

	thought_of_the_day = get_thought_of_the_day()
	phamos_emoji = random.choice(PHAMOS_EMOJIS)
	reply_emoji = random.choice(REPLY_EMOJIS)
	today_compact = datetime.now().strftime("%Y%m%d")

	bot = frappe.get_doc("Raven Bot", settings.raven_bot)
	channel_id = settings.raven_channel
	bot.add_to_channel(channel_id)

	parent_text = f"{today_compact} - Daily {phamos_emoji}"
	parent_message_id = _bot_send_message(bot, channel_id, parent_text)

	create_thread(parent_message_id)

	reply_message = (
		f"Good Morning 'phamos' {phamos_emoji} 🙏\n> {thought_of_the_day} {reply_emoji}"
	)
	_bot_send_message(bot, parent_message_id, reply_message, markdown=True)

	if settings.enable_daily_image:
		if post_image_sync:
			try:
				_post_daily_image(settings, settings.raven_bot, parent_message_id, thought_of_the_day)
			except Exception:
				frappe.log_error(
					frappe.get_traceback(),
					"Raven Daily Thread: failed to post daily image",
				)
			_post_birthday_wishes_after_thread(
				parent_message_id, settings.raven_bot, today_date
			)
		else:
			_enqueue_daily_image(
				settings, parent_message_id, thought_of_the_day, today_date
			)
	else:
		_post_birthday_wishes_after_thread(
			parent_message_id, settings.raven_bot, today_date
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
	_create_raven_thread(settings, today_date, post_image_sync=True)
	return {"status": "ok", "date": today_date}
