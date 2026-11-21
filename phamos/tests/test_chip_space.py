# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Chip Space slice 1 (#2054): my own chip's remembered position and the dummy chips."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.api import chip_space


class ChipSpaceTestCase(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.defaults.clear_user_default(chip_space.POSITION_KEY)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_spawn_when_nothing_is_stored(self):
		space = chip_space.get_space()
		self.assertEqual((space["me"]["x"], space["me"]["y"]), (chip_space.COLS // 2, chip_space.ROWS // 2))
		self.assertEqual((space["cols"], space["rows"]), (chip_space.COLS, chip_space.ROWS))
		self.assertEqual(space["me"]["user"], "Administrator")

	def test_free_position_round_trip(self):
		chip_space.save_my_position(3.456, "7.1")
		me = chip_space.get_space()["me"]
		self.assertEqual((me["x"], me["y"]), (3.46, 7.1))

	def test_clamped_to_the_grid(self):
		self.assertEqual(chip_space.save_my_position(-5, 999), {"x": 0.0, "y": chip_space.ROWS - 1.0})
		self.assertEqual(chip_space.save_my_position("abc", "nan"), {"x": 0.0, "y": 0.0})

	def test_broken_stored_value_falls_back_to_spawn(self):
		frappe.defaults.set_user_default(chip_space.POSITION_KEY, "not json")
		me = chip_space.get_space()["me"]
		self.assertEqual((me["x"], me["y"]), (chip_space.COLS // 2, chip_space.ROWS // 2))

	def test_dummies_from_site_config(self):
		dummies = [{"user": "Guest", "x": 5, "y": 6}, {"user": "Administrator", "x": 1, "y": 1}, {"user": "nobody@example.com"}, "junk"]
		with patch.dict(frappe.conf, {chip_space.DUMMIES_CONF_KEY: dummies}):
			others = chip_space.get_space()["others"]
		# Guest is an enabled user; myself and unknown users are left out.
		self.assertEqual([(o["user"], o["x"], o["y"]) for o in others], [("Guest", 5.0, 6.0)])

	def test_no_dummies_without_site_config(self):
		with patch.dict(frappe.conf, {chip_space.DUMMIES_CONF_KEY: None}):
			self.assertEqual(chip_space.get_space()["others"], [])

	def test_guest_is_refused(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			chip_space.get_space()
		with self.assertRaises(frappe.PermissionError):
			chip_space.save_my_position(1, 1)


class ChipSpacePresenceTestCase(FrappeTestCase):
	"""Slice 2 (#2055): presence in the cache, moves and leaves over realtime."""

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.cache.delete_value(chip_space.PRESENCE_CACHE_KEY)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.cache.delete_value(chip_space.PRESENCE_CACHE_KEY)
		frappe.db.rollback()

	def _put(self, user, x, y, age=0):
		frappe.cache.hset(
			chip_space.PRESENCE_CACHE_KEY, user, {"user": user, "full_name": user, "user_image": "", "x": x, "y": y, "ts": chip_space.time.time() - age}
		)

	def test_heartbeat_joins_and_publishes(self):
		with patch.object(chip_space.frappe, "publish_realtime") as publish:
			chip = chip_space.heartbeat(4, 5)
		self.assertEqual((chip["user"], chip["x"], chip["y"]), ("Administrator", 4.0, 5.0))
		self.assertEqual(publish.call_args.args[0], chip_space.EVENT_PRESENCE)
		self.assertIn("Administrator", {c["user"] for c in chip_space._online()})

	def test_others_online_but_not_me_and_not_stale(self):
		self._put("Administrator", 1, 1)
		self._put("someone@example.com", 2, 3)
		self._put("gone@example.com", 6, 6, age=chip_space.PRESENCE_TTL + 5)
		with patch.dict(frappe.conf, {chip_space.DUMMIES_CONF_KEY: None}):
			others = chip_space.get_space()["others"]
		self.assertEqual([(o["user"], o["x"], o["y"]) for o in others], [("someone@example.com", 2, 3)])
		self.assertNotIn("ts", others[0])
		# the stale entry was dropped from the cache
		self.assertIsNone(frappe.cache.hget(chip_space.PRESENCE_CACHE_KEY, "gone@example.com"))

	def test_move_needs_presence_and_is_clamped(self):
		with patch.object(chip_space.frappe, "publish_realtime") as publish:
			self.assertIsNone(chip_space.move(3, 3))
			publish.assert_not_called()
			chip_space.heartbeat(1, 1)
			self.assertEqual(chip_space.move(99, -1), {"user": "Administrator", "x": chip_space.COLS - 1.0, "y": 0.0})
		self.assertEqual(publish.call_args.args[0], chip_space.EVENT_MOVE)

	def test_move_throttled_per_user(self):
		chip_space.heartbeat(1, 1)
		frappe.cache.delete_value(f"phamos_chip_space_moves:{frappe.session.user}")
		with patch.object(chip_space.frappe, "publish_realtime"):
			results = [chip_space.move(2, 2) for _ in range(chip_space.MOVE_LIMIT + 3)]
		self.assertTrue(all(results[: chip_space.MOVE_LIMIT]))
		self.assertEqual(results[chip_space.MOVE_LIMIT :], [None, None, None])

	def test_leave_removes_and_publishes(self):
		chip_space.heartbeat(1, 1)
		with patch.object(chip_space.frappe, "publish_realtime") as publish:
			chip_space.leave()
		self.assertEqual(publish.call_args.args, (chip_space.EVENT_LEAVE, {"user": "Administrator"}))
		self.assertEqual(chip_space._online(), [])

	def test_website_user_refused(self):
		email = "chip-space-web@example.com"
		if not frappe.db.exists("User", email):
			frappe.get_doc({"doctype": "User", "email": email, "first_name": "Web", "user_type": "Website User", "send_welcome_email": 0}).insert(ignore_permissions=True)
		frappe.set_user(email)
		with self.assertRaises(frappe.PermissionError):
			chip_space.heartbeat(1, 1)


class ChipSpaceEncounterTestCase(FrappeTestCase):
	"""Slice 3 (#2056): two chips that meet get a temporary private Raven channel."""

	A = "chip-space-a@example.com"
	B = "chip-space-b@example.com"
	C = "chip-space-c@example.com"

	def setUp(self):
		frappe.set_user("Administrator")
		for email in (self.A, self.B, self.C):
			if not frappe.db.exists("User", email):
				user = frappe.get_doc(
					{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
				).insert(ignore_permissions=True)
				user.add_roles("Raven User")
		if not frappe.get_all("Raven Workspace", limit=1):
			frappe.get_doc({"doctype": "Raven Workspace", "workspace_name": "Chip Space Test", "type": "Public"}).insert(
				ignore_permissions=True
			)
		frappe.cache.delete_value(chip_space.PRESENCE_CACHE_KEY)
		self._put(self.A, 5, 5)
		self._put(self.B, 6, 5)
		self._put(self.C, 30, 20)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.cache.delete_value(chip_space.PRESENCE_CACHE_KEY)
		frappe.db.rollback()

	def _put(self, user, x, y):
		frappe.cache.hset(
			chip_space.PRESENCE_CACHE_KEY, user, {"user": user, "x": x, "y": y, "ts": chip_space.time.time()}
		)

	def _open(self, as_user, with_user):
		frappe.set_user(as_user)
		with patch.dict(frappe.conf, {chip_space.DUMMIES_CONF_KEY: None}):
			return chip_space.open_encounter(with_user)

	def test_meeting_opens_one_private_channel_for_both(self):
		first = self._open(self.A, self.B)
		second = self._open(self.B, self.A)
		self.assertEqual(first["encounter"], second["encounter"])
		self.assertEqual((first["with"], second["with"]), (self.B, self.A))
		channel = frappe.get_doc("Raven Channel", first["channel"])
		self.assertEqual(channel.type, "Private")
		members = set(frappe.get_all("Raven Channel Member", filters={"channel_id": channel.name}, pluck="user_id"))
		self.assertEqual(members, {self.A, self.B})
		self.assertEqual(
			frappe.db.count("Chip Space Encounter", {"pair_key": chip_space._pair_key(self.A, self.B)}), 1
		)

	def test_video_room_per_encounter(self):
		with patch.dict(frappe.conf, {"chip_space_jitsi_domain": None, "chip_space_video": None}):
			first = self._open(self.A, self.B)
			again = self._open(self.B, self.A)
			self.assertEqual(first["video"]["domain"], "meet.jit.si")
			self.assertRegex(first["video"]["room"], r"^phamos-chip-[0-9a-f]{24}$")
			self.assertEqual(again["video"], first["video"])
		with patch.dict(frappe.conf, {"chip_space_video": 0}):
			self.assertIsNone(self._open(self.A, self.B)["video"])
		with patch.dict(frappe.conf, {"chip_space_jitsi_domain": "evil.example/x?y", "chip_space_video": None}):
			self.assertIsNone(self._open(self.A, self.B)["video"])

	def test_too_far_apart(self):
		with self.assertRaises(frappe.ValidationError):
			self._open(self.A, self.C)

	def test_messages_reach_both_and_stay_private(self):
		encounter = self._open(self.A, self.B)["encounter"]
		with patch.object(chip_space.frappe, "publish_realtime") as publish:
			row = chip_space.send_encounter_message(encounter, "Hi <b>there</b>\nline 2")
		mine = [c for c in publish.call_args_list if c.args[0] == chip_space.EVENT_MESSAGE]
		self.assertEqual({c.kwargs["user"] for c in mine}, {self.A, self.B})
		self.assertEqual(row["owner"], self.A)
		frappe.set_user(self.B)
		messages = chip_space.get_encounter(encounter)["messages"]
		self.assertEqual([m["owner"] for m in messages], [self.A])
		# shown as text: the tags the user typed come back as text, not markup
		self.assertEqual(messages[0]["text"], "Hi <b>there</b>\nline 2")
		frappe.set_user(self.C)
		with self.assertRaises(frappe.PermissionError):
			chip_space.get_encounter(encounter)
		with self.assertRaises(frappe.PermissionError):
			chip_space.send_encounter_message(encounter, "let me in")

	def test_empty_message_refused(self):
		encounter = self._open(self.A, self.B)["encounter"]
		with self.assertRaises(frappe.ValidationError):
			chip_space.send_encounter_message(encounter, "   ")

	def test_dummy_answers_yes_no_or_maybe(self):
		encounter = self._open(self.A, self.B)["encounter"]
		with patch.dict(frappe.conf, {chip_space.DUMMIES_CONF_KEY: [{"user": self.B, "x": 6, "y": 5}]}):
			with patch.object(chip_space.frappe, "enqueue") as enqueue:
				chip_space.send_encounter_message(encounter, "Coffee?")
			self.assertEqual(enqueue.call_args.kwargs["dummy"], self.B)
			with patch.object(chip_space, "DUMMY_REPLY_DELAY", 0), patch.object(chip_space.frappe, "publish_realtime"):
				chip_space.dummy_reply(encounter, self.B)
			frappe.set_user(self.A)
			messages = chip_space.get_encounter(encounter)["messages"]
		self.assertEqual(messages[-1]["owner"], self.B)
		self.assertIn(messages[-1]["text"], ("Yes", "No", "Maybe"))

	def test_real_people_get_no_auto_reply(self):
		encounter = self._open(self.A, self.B)["encounter"]
		with patch.dict(frappe.conf, {chip_space.DUMMIES_CONF_KEY: None}):
			with patch.object(chip_space.frappe, "enqueue") as enqueue:
				chip_space.send_encounter_message(encounter, "Coffee?")
		enqueue.assert_not_called()


	# --- Burn notice, save, burn (#2057)

	def _chat(self):
		"""A opens the encounter with B and writes one message; returns the encounter row."""
		encounter = self._open(self.A, self.B)["encounter"]
		with patch.object(chip_space.frappe, "publish_realtime"), patch.object(chip_space.frappe, "enqueue"):
			chip_space.send_encounter_message(encounter, "Lunch?")
		return frappe.db.get_value("Chip Space Encounter", encounter, chip_space.ENCOUNTER_FIELDS, as_dict=True)

	def _no_trace(self, doc, messages):
		self.assertFalse(frappe.db.exists("Chip Space Encounter", doc.name))
		self.assertFalse(frappe.db.exists("Raven Channel", doc.raven_channel))
		self.assertFalse(
			frappe.db.exists("Deleted Document", {"deleted_doctype": ("in", ["Raven Message", "Raven Channel", "Chip Space Encounter"]), "deleted_name": ("in", [doc.name, doc.raven_channel, *messages])})
		)

	def test_parting_starts_the_burn_notice_for_both(self):
		doc = self._chat()
		with patch.object(chip_space.frappe, "publish_realtime") as publish:
			notice = chip_space.part_encounter(doc.name)
		self.assertEqual(frappe.db.get_value("Chip Space Encounter", doc.name, "status"), "Parting")
		self.assertAlmostEqual(notice["burn_in"], chip_space.BURN_SECONDS, delta=2)
		self.assertEqual((notice["with"], notice["saved_by_me"]), (self.B, False))
		notices = [c for c in publish.call_args_list if c.args[0] == chip_space.EVENT_BURN_NOTICE]
		self.assertEqual({c.kwargs["user"] for c in notices}, {self.A, self.B})

	def test_parting_from_an_empty_chat_leaves_nothing(self):
		encounter = self._open(self.A, self.B)
		doc = frappe.db.get_value("Chip Space Encounter", encounter["encounter"], chip_space.ENCOUNTER_FIELDS, as_dict=True)
		self.assertIsNone(chip_space.part_encounter(doc.name))
		self._no_trace(doc, [])

	def test_meeting_again_cancels_the_burn(self):
		doc = self._chat()
		chip_space.part_encounter(doc.name)
		again = self._open(self.B, self.A)
		self.assertEqual(again["encounter"], doc.name)
		self.assertEqual([m["text"] for m in again["messages"]], ["Lunch?"])
		self.assertEqual(frappe.db.get_value("Chip Space Encounter", doc.name, ["status", "burn_at"]), ("Open", None))

	def test_one_save_is_not_enough_both_saves_move_into_the_dm(self):
		doc = self._chat()
		messages = frappe.get_all("Raven Message", filters={"channel_id": doc.raven_channel}, pluck="name")
		chip_space.part_encounter(doc.name)
		with patch.object(chip_space.frappe, "publish_realtime"):
			self.assertEqual(chip_space.save_encounter(doc.name), {"saved": False})
			frappe.set_user(self.B)
			result = chip_space.save_encounter(doc.name)
		self.assertTrue(result["saved"])
		dm = frappe.get_doc("Raven Channel", result["dm_channel"])
		self.assertTrue(dm.is_direct_message)
		moved = frappe.get_all("Raven Message", filters={"channel_id": dm.name}, fields=["name", "owner"])
		self.assertEqual({(m.name, m.owner) for m in moved}, {(name, self.A) for name in messages})
		self._no_trace(doc, [])

	def test_burn_only_when_due(self):
		doc = self._chat()
		messages = frappe.get_all("Raven Message", filters={"channel_id": doc.raven_channel}, pluck="name")
		chip_space.part_encounter(doc.name)
		chip_space.save_encounter(doc.name)  # only one of the two
		self.assertEqual(chip_space.burn_if_due(doc.name), {"burned": False})
		frappe.db.set_value("Chip Space Encounter", doc.name, "burn_at", chip_space.add_to_date(chip_space.now_datetime(), seconds=-1))
		with patch.object(chip_space.frappe, "publish_realtime"):
			self.assertEqual(chip_space.burn_if_due(doc.name), {"burned": True})
		self.assertFalse(frappe.db.exists("Raven Message", {"name": ("in", messages)}))
		self._no_trace(doc, messages)

	def test_scheduler_burns_overdue_and_parts_when_someone_is_gone(self):
		overdue = self._chat()
		chip_space.part_encounter(overdue.name)
		frappe.db.set_value("Chip Space Encounter", overdue.name, "burn_at", chip_space.add_to_date(chip_space.now_datetime(), seconds=-5))
		self._put(self.C, 7, 5)
		frappe.set_user(self.C)
		with patch.dict(frappe.conf, {chip_space.DUMMIES_CONF_KEY: None}):
			open_one = chip_space.open_encounter(self.B)["encounter"]
			with patch.object(chip_space.frappe, "publish_realtime"), patch.object(chip_space.frappe, "enqueue"):
				chip_space.send_encounter_message(open_one, "Hi B")
			frappe.cache.hdel(chip_space.PRESENCE_CACHE_KEY, self.C)  # C closed the tab
			with patch.object(chip_space.frappe.db, "commit"), patch.object(chip_space.frappe, "publish_realtime"):
				chip_space.burn_due_encounters()
		self.assertFalse(frappe.db.exists("Chip Space Encounter", overdue.name))
		self.assertEqual(frappe.db.get_value("Chip Space Encounter", open_one, "status"), "Parting")

	def test_leaving_the_page_parts(self):
		doc = self._chat()
		with patch.object(chip_space.frappe, "publish_realtime"):
			chip_space.leave()
		self.assertEqual(frappe.db.get_value("Chip Space Encounter", doc.name, "status"), "Parting")
		frappe.set_user(self.B)
		with patch.dict(frappe.conf, {chip_space.DUMMIES_CONF_KEY: None}):
			self.assertEqual([n["encounter"] for n in chip_space.get_space()["notices"]], [doc.name])


class ChipSpaceBackgroundTestCase(FrappeTestCase):
	"""The Space's shared background image."""

	def setUp(self):
		frappe.set_user("Administrator")
		self.saved = frappe.db.get_default(chip_space.BACKGROUND_KEY)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _png(self, colour="red"):
		from io import BytesIO

		from PIL import Image

		buffer = BytesIO()
		Image.new("RGB", (4, 4), colour).save(buffer, format="PNG")
		return buffer.getvalue()

	def test_image_becomes_the_background_and_replaces_the_old_one(self):
		with patch.object(chip_space.frappe, "publish_realtime") as publish:
			first = chip_space._store_background(self._png(), "My Office.png")
			first_file = chip_space._background()["file"]
			second = chip_space._store_background(self._png("blue"), "beach.png")
		self.assertTrue(first.startswith("/files/chip-space-My-Office"))
		self.assertEqual(chip_space.get_space()["background"], second)
		self.assertFalse(frappe.db.exists("File", first_file))
		self.assertEqual(publish.call_args.args[0], chip_space.EVENT_BACKGROUND)

	def test_not_an_image_is_refused(self):
		svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
		for content in (svg, b"plain text", b""):
			with self.assertRaises(frappe.ValidationError):
				chip_space._store_background(content, "evil.png")

	def test_too_big_is_refused(self):
		with patch.object(chip_space, "BACKGROUND_MAX_BYTES", 10):
			with self.assertRaises(frappe.ValidationError):
				chip_space._store_background(self._png(), "big.png")

	def test_remove(self):
		with patch.object(chip_space.frappe, "publish_realtime"):
			chip_space._store_background(self._png(), "x.png")
			chip_space.remove_background()
		self.assertEqual(chip_space.get_space()["background"], "")
