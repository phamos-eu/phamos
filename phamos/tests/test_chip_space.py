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
