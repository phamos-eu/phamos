# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Ophice slice 1 (#2054): my own chip's remembered position and the dummy chips."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.api import ophice


class OphiceTestCase(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.defaults.clear_user_default(ophice.POSITION_KEY)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_spawn_when_nothing_is_stored(self):
		space = ophice.get_space()
		self.assertEqual((space["me"]["x"], space["me"]["y"]), (ophice.COLS // 2, ophice.ROWS // 2))
		self.assertEqual((space["cols"], space["rows"]), (ophice.COLS, ophice.ROWS))
		self.assertEqual(space["me"]["user"], "Administrator")

	def test_free_position_round_trip(self):
		ophice.save_my_position(3.456, "7.1")
		me = ophice.get_space()["me"]
		self.assertEqual((me["x"], me["y"]), (3.46, 7.1))

	def test_clamped_to_the_grid(self):
		self.assertEqual(ophice.save_my_position(-5, 999), {"x": 0.0, "y": ophice.ROWS - 1.0})
		self.assertEqual(ophice.save_my_position("abc", "nan"), {"x": 0.0, "y": 0.0})

	def test_broken_stored_value_falls_back_to_spawn(self):
		frappe.defaults.set_user_default(ophice.POSITION_KEY, "not json")
		me = ophice.get_space()["me"]
		self.assertEqual((me["x"], me["y"]), (ophice.COLS // 2, ophice.ROWS // 2))

	def test_dummies_from_site_config(self):
		dummies = [{"user": "Guest", "x": 5, "y": 6}, {"user": "Administrator", "x": 1, "y": 1}, {"user": "nobody@example.com"}, "junk"]
		with patch.dict(frappe.conf, {ophice.DUMMIES_CONF_KEY: dummies}):
			others = ophice.get_space()["others"]
		# Guest is an enabled user; myself and unknown users are left out.
		self.assertEqual([(o["user"], o["x"], o["y"]) for o in others], [("Guest", 5.0, 6.0)])

	def test_no_dummies_without_site_config(self):
		# Real away users of the site would show up too: not part of this test.
		with patch.dict(frappe.conf, {ophice.DUMMIES_CONF_KEY: None}), patch.object(ophice, "_away_offline", return_value=[]):
			self.assertEqual(ophice.get_space()["others"], [])

	def test_guest_is_refused(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			ophice.get_space()
		with self.assertRaises(frappe.PermissionError):
			ophice.save_my_position(1, 1)


class OphicePresenceTestCase(FrappeTestCase):
	"""Slice 2 (#2055): presence in the cache, moves and leaves over realtime."""

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.cache.delete_value(ophice.PRESENCE_CACHE_KEY)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.cache.delete_value(ophice.PRESENCE_CACHE_KEY)
		frappe.db.rollback()

	def _put(self, user, x, y, age=0):
		frappe.cache.hset(
			ophice.PRESENCE_CACHE_KEY, user, {"user": user, "full_name": user, "user_image": "", "x": x, "y": y, "ts": ophice.time.time() - age}
		)

	def test_heartbeat_joins_and_publishes(self):
		with patch.object(ophice.frappe, "publish_realtime") as publish:
			chip = ophice.heartbeat(4, 5)
		self.assertEqual((chip["user"], chip["x"], chip["y"]), ("Administrator", 4.0, 5.0))
		self.assertEqual(publish.call_args.args[0], ophice.EVENT_PRESENCE)
		self.assertIn("Administrator", {c["user"] for c in ophice._online()})

	def test_others_online_but_not_me_and_not_stale(self):
		self._put("Administrator", 1, 1)
		self._put("someone@example.com", 2, 3)
		self._put("gone@example.com", 6, 6, age=ophice.PRESENCE_TTL + 5)
		with patch.dict(frappe.conf, {ophice.DUMMIES_CONF_KEY: None}):
			others = ophice.get_space()["others"]
		self.assertEqual([(o["user"], o["x"], o["y"]) for o in others], [("someone@example.com", 2, 3)])
		self.assertNotIn("ts", others[0])
		# the stale entry was dropped from the cache
		self.assertIsNone(frappe.cache.hget(ophice.PRESENCE_CACHE_KEY, "gone@example.com"))

	def test_move_needs_presence_and_is_clamped(self):
		with patch.object(ophice.frappe, "publish_realtime") as publish:
			self.assertIsNone(ophice.move(3, 3))
			publish.assert_not_called()
			ophice.heartbeat(1, 1)
			self.assertEqual(ophice.move(99, -1), {"user": "Administrator", "x": ophice.COLS - 1.0, "y": 0.0})
		self.assertEqual(publish.call_args.args[0], ophice.EVENT_MOVE)

	def test_move_throttled_per_user(self):
		ophice.heartbeat(1, 1)
		frappe.cache.delete_value(f"phamos_ophice_moves:{frappe.session.user}")
		with patch.object(ophice.frappe, "publish_realtime"):
			results = [ophice.move(2, 2) for _ in range(ophice.MOVE_LIMIT + 3)]
		self.assertTrue(all(results[: ophice.MOVE_LIMIT]))
		self.assertEqual(results[ophice.MOVE_LIMIT :], [None, None, None])

	def test_leave_removes_and_publishes(self):
		ophice.heartbeat(1, 1)
		with patch.object(ophice.frappe, "publish_realtime") as publish:
			ophice.leave()
		# Other events may follow (the site's own encounters of Administrator part too).
		self.assertIn(((ophice.EVENT_LEAVE, {"user": "Administrator"}),), [(c.args,) for c in publish.call_args_list])
		self.assertEqual(ophice._online(), [])

	def test_website_user_refused(self):
		email = "ophice-web@example.com"
		if not frappe.db.exists("User", email):
			frappe.get_doc({"doctype": "User", "email": email, "first_name": "Web", "user_type": "Website User", "send_welcome_email": 0}).insert(ignore_permissions=True)
		frappe.set_user(email)
		with self.assertRaises(frappe.PermissionError):
			ophice.heartbeat(1, 1)


class OphiceEncounterTestCase(FrappeTestCase):
	"""Slice 3 (#2056): two chips that meet get a temporary private Raven channel."""

	A = "ophice-a@example.com"
	B = "ophice-b@example.com"
	C = "ophice-c@example.com"

	def setUp(self):
		frappe.set_user("Administrator")
		for email in (self.A, self.B, self.C):
			if not frappe.db.exists("User", email):
				user = frappe.get_doc(
					{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
				).insert(ignore_permissions=True)
				user.add_roles("Raven User")
		if not frappe.get_all("Raven Workspace", limit=1):
			frappe.get_doc({"doctype": "Raven Workspace", "workspace_name": "Ophice Test", "type": "Public"}).insert(
				ignore_permissions=True
			)
		frappe.cache.delete_value(ophice.PRESENCE_CACHE_KEY)
		self._put(self.A, 5, 5)
		self._put(self.B, 6, 5)
		self._put(self.C, 30, 20)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.cache.delete_value(ophice.PRESENCE_CACHE_KEY)
		frappe.db.rollback()

	def _put(self, user, x, y):
		frappe.cache.hset(
			ophice.PRESENCE_CACHE_KEY, user, {"user": user, "x": x, "y": y, "ts": ophice.time.time()}
		)

	def _open(self, as_user, with_user):
		frappe.set_user(as_user)
		with patch.dict(frappe.conf, {ophice.DUMMIES_CONF_KEY: None}):
			return ophice.open_encounter(with_user)

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
			frappe.db.count("Ophice Encounter", {"pair_key": ophice._pair_key(self.A, self.B)}), 1
		)

	def test_video_room_per_encounter(self):
		with patch.dict(frappe.conf, {"ophice_jitsi_domain": None, "ophice_video": None}):
			first = self._open(self.A, self.B)
			again = self._open(self.B, self.A)
			self.assertEqual(first["video"]["domain"], "meet.jit.si")
			self.assertRegex(first["video"]["room"], r"^ophice-[0-9a-f]{24}$")
			self.assertEqual(again["video"], first["video"])
		with patch.dict(frappe.conf, {"ophice_video": 0}):
			self.assertIsNone(self._open(self.A, self.B)["video"])
		with patch.dict(frappe.conf, {"ophice_jitsi_domain": "evil.example/x?y", "ophice_video": None}):
			self.assertIsNone(self._open(self.A, self.B)["video"])

	def test_both_pages_opening_at_once_get_the_same_encounter(self):
		"""The page that loses the race to insert takes the winner's encounter (Pair Key unique)."""
		first = self._open(self.A, self.B)
		real = ophice._open_encounter_name
		frappe.local.message_log = []
		# B's request did not see A's row yet when it looked, so it tries to insert too.
		with patch.object(ophice, "_open_encounter_name", side_effect=[None, real(ophice._pair_key(self.A, self.B))]):
			second = self._open(self.B, self.A)
		self.assertEqual(second["encounter"], first["encounter"])
		self.assertEqual(frappe.db.count("Ophice Encounter", {"pair_key": ophice._pair_key(self.A, self.B)}), 1)
		# No "Pair Key must be unique" left for the page to show.
		self.assertFalse(any("must be unique" in str(m) for m in frappe.local.message_log))
		# The users and the first encounter of this test survived: only the failed insert was undone.
		self.assertTrue(frappe.db.exists("User", self.A))

	def test_open_holds_the_pair_lock_until_the_end(self):
		"""Two pages opening at once wait for each other instead of racing (deadlock seen live)."""
		self._open(self.A, self.B)
		name = "phamos_ophice_" + ophice.hashlib.md5(ophice._pair_key(self.A, self.B).encode()).hexdigest()
		# Held by this connection (still in the request's transaction)...
		self.assertEqual(frappe.db.sql("SELECT IS_USED_LOCK(%s) = CONNECTION_ID()", (name,))[0][0], 1)
		frappe.db.rollback()
		# ...and released with the transaction.
		self.assertIsNone(frappe.db.sql("SELECT IS_USED_LOCK(%s)", (name,))[0][0])

	def test_starting_a_chat_opens_it_on_the_other_side(self):
		with patch.object(ophice.frappe, "publish_realtime") as publish:
			started = self._open(self.A, self.B)
		calls = [c for c in publish.call_args_list if c.args[0] == ophice.EVENT_STARTED]
		self.assertEqual(len(calls), 1)
		self.assertEqual(calls[0].kwargs["user"], self.B)
		self.assertEqual(calls[0].args[1], {"encounter": started["encounter"], "with": self.A})

	def test_too_far_apart(self):
		with self.assertRaises(frappe.ValidationError):
			self._open(self.A, self.C)

	def test_messages_reach_both_and_stay_private(self):
		encounter = self._open(self.A, self.B)["encounter"]
		with patch.object(ophice.frappe, "publish_realtime") as publish:
			row = ophice.send_encounter_message(encounter, "Hi <b>there</b>\nline 2")
		mine = [c for c in publish.call_args_list if c.args[0] == ophice.EVENT_MESSAGE]
		self.assertEqual({c.kwargs["user"] for c in mine}, {self.A, self.B})
		self.assertEqual(row["owner"], self.A)
		frappe.set_user(self.B)
		messages = ophice.get_encounter(encounter)["messages"]
		self.assertEqual([m["owner"] for m in messages], [self.A])
		# shown as text: the tags the user typed come back as text, not markup
		self.assertEqual(messages[0]["text"], "Hi <b>there</b>\nline 2")
		frappe.set_user(self.C)
		with self.assertRaises(frappe.PermissionError):
			ophice.get_encounter(encounter)
		with self.assertRaises(frappe.PermissionError):
			ophice.send_encounter_message(encounter, "let me in")

	def test_empty_message_refused(self):
		encounter = self._open(self.A, self.B)["encounter"]
		with self.assertRaises(frappe.ValidationError):
			ophice.send_encounter_message(encounter, "   ")

	def test_dummy_answers_yes_no_or_maybe(self):
		encounter = self._open(self.A, self.B)["encounter"]
		with patch.dict(frappe.conf, {ophice.DUMMIES_CONF_KEY: [{"user": self.B, "x": 6, "y": 5}]}):
			with patch.object(ophice.frappe, "enqueue") as enqueue:
				ophice.send_encounter_message(encounter, "Coffee?")
			self.assertEqual(enqueue.call_args.kwargs["dummy"], self.B)
			with patch.object(ophice, "DUMMY_REPLY_DELAY", 0), patch.object(ophice.frappe, "publish_realtime"):
				ophice.dummy_reply(encounter, self.B)
			frappe.set_user(self.A)
			messages = ophice.get_encounter(encounter)["messages"]
		self.assertEqual(messages[-1]["owner"], self.B)
		self.assertIn(messages[-1]["text"], ("Yes", "No", "Maybe"))

	def test_real_people_get_no_auto_reply(self):
		encounter = self._open(self.A, self.B)["encounter"]
		with patch.dict(frappe.conf, {ophice.DUMMIES_CONF_KEY: None}):
			with patch.object(ophice.frappe, "enqueue") as enqueue:
				ophice.send_encounter_message(encounter, "Coffee?")
		enqueue.assert_not_called()


	# --- Burn notice, save, burn (#2057)

	def _chat(self):
		"""A opens the encounter with B and writes one message; returns the encounter row."""
		encounter = self._open(self.A, self.B)["encounter"]
		with patch.object(ophice.frappe, "publish_realtime"), patch.object(ophice.frappe, "enqueue"):
			ophice.send_encounter_message(encounter, "Lunch?")
		return frappe.db.get_value("Ophice Encounter", encounter, ophice.ENCOUNTER_FIELDS, as_dict=True)

	def _no_trace(self, doc, messages):
		self.assertFalse(frappe.db.exists("Ophice Encounter", doc.name))
		self.assertFalse(frappe.db.exists("Raven Channel", doc.raven_channel))
		self.assertFalse(
			frappe.db.exists("Deleted Document", {"deleted_doctype": ("in", ["Raven Message", "Raven Channel", "Ophice Encounter"]), "deleted_name": ("in", [doc.name, doc.raven_channel, *messages])})
		)

	def test_parting_starts_the_burn_notice_for_both(self):
		doc = self._chat()
		with patch.object(ophice.frappe, "publish_realtime") as publish:
			notice = ophice.part_encounter(doc.name)
		self.assertEqual(frappe.db.get_value("Ophice Encounter", doc.name, "status"), "Parting")
		self.assertAlmostEqual(notice["burn_in"], ophice.BURN_SECONDS, delta=2)
		self.assertEqual((notice["with"], notice["saved_by_me"]), (self.B, False))
		notices = [c for c in publish.call_args_list if c.args[0] == ophice.EVENT_BURN_NOTICE]
		self.assertEqual({c.kwargs["user"] for c in notices}, {self.A, self.B})

	def test_parting_from_an_empty_chat_leaves_nothing(self):
		encounter = self._open(self.A, self.B)
		doc = frappe.db.get_value("Ophice Encounter", encounter["encounter"], ophice.ENCOUNTER_FIELDS, as_dict=True)
		self.assertIsNone(ophice.part_encounter(doc.name))
		self._no_trace(doc, [])

	def test_meeting_again_cancels_the_burn(self):
		doc = self._chat()
		ophice.part_encounter(doc.name)
		again = self._open(self.B, self.A)
		self.assertEqual(again["encounter"], doc.name)
		self.assertEqual([m["text"] for m in again["messages"]], ["Lunch?"])
		self.assertEqual(frappe.db.get_value("Ophice Encounter", doc.name, ["status", "burn_at"]), ("Open", None))

	def test_one_save_is_not_enough_both_saves_move_into_the_dm(self):
		doc = self._chat()
		messages = frappe.get_all("Raven Message", filters={"channel_id": doc.raven_channel}, pluck="name")
		ophice.part_encounter(doc.name)
		with patch.object(ophice.frappe, "publish_realtime"):
			self.assertEqual(ophice.save_encounter(doc.name), {"saved": False})
			frappe.set_user(self.B)
			result = ophice.save_encounter(doc.name)
		self.assertTrue(result["saved"])
		dm = frappe.get_doc("Raven Channel", result["dm_channel"])
		self.assertTrue(dm.is_direct_message)
		moved = frappe.get_all("Raven Message", filters={"channel_id": dm.name}, fields=["name", "owner"])
		self.assertEqual({(m.name, m.owner) for m in moved}, {(name, self.A) for name in messages})
		self._no_trace(doc, [])

	def test_burn_only_when_due(self):
		doc = self._chat()
		messages = frappe.get_all("Raven Message", filters={"channel_id": doc.raven_channel}, pluck="name")
		ophice.part_encounter(doc.name)
		ophice.save_encounter(doc.name)  # only one of the two
		self.assertEqual(ophice.burn_if_due(doc.name), {"burned": False})
		frappe.db.set_value("Ophice Encounter", doc.name, "burn_at", ophice.add_to_date(ophice.now_datetime(), seconds=-1))
		with patch.object(ophice.frappe, "publish_realtime"):
			self.assertEqual(ophice.burn_if_due(doc.name), {"burned": True})
		self.assertFalse(frappe.db.exists("Raven Message", {"name": ("in", messages)}))
		self._no_trace(doc, messages)

	def test_scheduler_burns_overdue_and_parts_when_someone_is_gone(self):
		overdue = self._chat()
		ophice.part_encounter(overdue.name)
		frappe.db.set_value("Ophice Encounter", overdue.name, "burn_at", ophice.add_to_date(ophice.now_datetime(), seconds=-5))
		self._put(self.C, 7, 5)
		frappe.set_user(self.C)
		with patch.dict(frappe.conf, {ophice.DUMMIES_CONF_KEY: None}):
			open_one = ophice.open_encounter(self.B)["encounter"]
			with patch.object(ophice.frappe, "publish_realtime"), patch.object(ophice.frappe, "enqueue"):
				ophice.send_encounter_message(open_one, "Hi B")
			frappe.cache.hdel(ophice.PRESENCE_CACHE_KEY, self.C)  # C closed the tab
			with patch.object(ophice.frappe.db, "commit"), patch.object(ophice.frappe, "publish_realtime"):
				ophice.burn_due_encounters()
		self.assertFalse(frappe.db.exists("Ophice Encounter", overdue.name))
		self.assertEqual(frappe.db.get_value("Ophice Encounter", open_one, "status"), "Parting")

	def test_leaving_the_page_parts(self):
		doc = self._chat()
		with patch.object(ophice.frappe, "publish_realtime"):
			ophice.leave()
		self.assertEqual(frappe.db.get_value("Ophice Encounter", doc.name, "status"), "Parting")
		frappe.set_user(self.B)
		with patch.dict(frappe.conf, {ophice.DUMMIES_CONF_KEY: None}):
			self.assertEqual([n["encounter"] for n in ophice.get_space()["notices"]], [doc.name])


class OphiceBackgroundTestCase(FrappeTestCase):
	"""Ophice's shared background image."""

	def setUp(self):
		frappe.set_user("Administrator")
		# Start without a background: replacing one deletes the previous File, and deleting a
		# File removes it from disk, which no rollback brings back. A site's real background
		# image must never be "the previous one" here (it was, once: a lost background).
		frappe.db.set_default(ophice.BACKGROUND_KEY, "")

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
		with patch.object(ophice.frappe, "publish_realtime") as publish:
			first = ophice._store_background(self._png(), "My Office.png")
			first_file = ophice._background()["file"]
			second = ophice._store_background(self._png("blue"), "beach.png")
		self.assertTrue(first.startswith("/files/ophice-My-Office"))
		self.assertEqual(ophice.get_space()["background"], second)
		self.assertFalse(frappe.db.exists("File", first_file))
		self.assertEqual(publish.call_args.args[0], ophice.EVENT_BACKGROUND)

	def test_not_an_image_is_refused(self):
		svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
		for content in (svg, b"plain text", b""):
			with self.assertRaises(frappe.ValidationError):
				ophice._store_background(content, "evil.png")

	def test_too_big_is_refused(self):
		with patch.object(ophice, "BACKGROUND_MAX_BYTES", 10):
			with self.assertRaises(frappe.ValidationError):
				ophice._store_background(self._png(), "big.png")

	def test_remove(self):
		with patch.object(ophice.frappe, "publish_realtime"):
			ophice._store_background(self._png(), "x.png")
			ophice.remove_background()
		self.assertEqual(ophice.get_space()["background"], "")


	def test_background_layout_is_clamped_and_shared(self):
		with patch.object(ophice.frappe, "publish_realtime"):
			with self.assertRaises(frappe.ValidationError):
				ophice.set_background_layout(0, 150, 10, 90)  # no background yet
			ophice._store_background(self._png(), "map.png")
			self.assertEqual(ophice.get_space()["background_layout"], {"fit": True, "scale": 100, "x": 50, "y": 50})
			layout = ophice.set_background_layout(0, 999, -5, 40)
		self.assertEqual(layout, {"fit": False, "scale": 300, "x": 0.0, "y": 40.0})
		self.assertEqual(ophice.get_space()["background_layout"], layout)

class OphiceAreaTestCase(FrappeTestCase):
	"""Meeting areas (#2060): rectangles with a fixed Jitsi meeting."""

	def setUp(self):
		frappe.set_user("Administrator")
		self.conf = patch.dict(frappe.conf, {"ophice_jitsi_domain": None, "ophice_jitsi_domains": ["jitsi.example.org"]})
		self.conf.start()
		self.publish = patch.object(ophice.frappe, "publish_realtime")
		self.publish.start()

	def tearDown(self):
		self.publish.stop()
		self.conf.stop()
		frappe.db.rollback()

	def test_save_reads_the_room_from_the_url_and_shows_in_the_space(self):
		name = ophice.save_area("Standup", " https://meet.jit.si/FullTimeDefencesRejectOverly ", 2, 3, 4, 2)
		area = next(a for a in ophice.get_space()["areas"] if a.name == name)
		self.assertEqual((area.jitsi_domain, area.jitsi_room), ("meet.jit.si", "FullTimeDefencesRejectOverly"))
		self.assertEqual((area.x, area.y, area.width, area.height), (2, 3, 4, 2))
		self.assertEqual(area.meeting_url, "https://meet.jit.si/FullTimeDefencesRejectOverly")

	def test_only_allowed_jitsi_servers_and_proper_rooms(self):
		self.assertEqual(ophice._parse_meeting_url("https://jitsi.example.org/Team_1"), ("jitsi.example.org", "Team_1"))
		for url in (
			"http://meet.jit.si/Room",  # not https
			"https://evil.example.com/Room",  # not an allowed server
			"https://meet.jit.si/",  # no room
			"https://meet.jit.si/a/b",  # not one room name
			"javascript:alert(1)",
		):
			with self.assertRaises(frappe.ValidationError, msg=url):
				ophice._parse_meeting_url(url)

	def test_rectangle_stays_inside_the_grid_and_areas_do_not_overlap(self):
		name = ophice.save_area("Corner", "https://meet.jit.si/CornerRoom", 38, 24, 10, 10)
		area = frappe.get_doc("Ophice Area", name)
		self.assertEqual((area.x, area.y, area.width, area.height), (38, 24, 2, 1))
		with self.assertRaises(frappe.ValidationError):
			ophice.save_area("Clash", "https://meet.jit.si/ClashRoom", 37, 23, 2, 2)
		# moving an area onto itself is fine
		ophice.save_area("Corner", "https://meet.jit.si/CornerRoom", 38, 23, 2, 2, name=name)

	def test_delete(self):
		name = ophice.save_area("Gone", "https://meet.jit.si/GoneRoom", 1, 1, 1, 1)
		ophice.delete_area(name)
		self.assertFalse(frappe.db.exists("Ophice Area", name))


	def test_every_area_gets_its_own_color(self):
		hues = []
		for i in range(5):
			name = ophice.save_area(f"Room {i}", f"https://meet.jit.si/ColorRoom{i}", i * 3, 0, 2, 2)
			hue = frappe.db.get_value("Ophice Area", name, "color_hue")
			self.assertTrue(0 <= hue < 360)
			for other in hues:
				self.assertGreaterEqual(min(abs(hue - other), 360 - abs(hue - other)), ophice.AREA_HUE_GAP)
			hues.append(hue)
		# Editing keeps the color.
		first = frappe.get_all("Ophice Area", filters={"title": "Room 1"}, fields=["name", "color_hue"])[0]
		ophice.save_area("Room 1b", "https://meet.jit.si/ColorRoom1", 3, 0, 2, 2, name=first.name)
		self.assertEqual(frappe.db.get_value("Ophice Area", first.name, "color_hue"), first.color_hue)


class OphiceStatusTestCase(FrappeTestCase):
	"""Be right back / Away (#2053): a note, and a return time as an instant in UTC."""

	USER = "ophice-a@example.com"

	def setUp(self):
		frappe.set_user("Administrator")
		if not frappe.db.exists("User", self.USER):
			user = frappe.get_doc(
				{"doctype": "User", "email": self.USER, "first_name": "ophice-a", "send_welcome_email": 0}
			).insert(ignore_permissions=True)
			user.add_roles("Raven User")
		frappe.set_user(self.USER)
		ophice.set_status("")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _in(self, **delta):
		from datetime import datetime, timedelta, timezone

		return (datetime.now(timezone.utc) + timedelta(**delta)).isoformat()

	def test_brb_with_note(self):
		status = ophice.set_status("brb", "<b>Coffee</b>", tz="Europe/Berlin")
		self.assertEqual((status["kind"], status["note"], status["tz"], status["until"]), ("brb", "Coffee", "Europe/Berlin", ""))
		self.assertEqual(ophice.get_space()["me"]["status"]["kind"], "brb")

	def test_away_time_is_stored_in_utc(self):
		# 15:30 in New York in winter is 20:30 UTC: the same instant for everyone.
		from datetime import datetime, timedelta, timezone

		back = (datetime.now(timezone.utc) + timedelta(days=1)).astimezone(timezone(timedelta(hours=-5)))
		back = back.replace(hour=15, minute=30, second=0, microsecond=0)
		status = ophice.set_status("away", "Doctor", back.isoformat(), "America/New_York")
		self.assertTrue(status["until"].endswith("T20:30:00Z"))
		self.assertEqual(status["tz"], "America/New_York")

	def test_away_needs_a_future_time_with_a_zone(self):
		for until in ("", "tomorrow", "2030-01-01T10:00:00", self._in(minutes=-5), self._in(days=30)):
			with self.assertRaises(frappe.ValidationError, msg=until):
				ophice.set_status("away", "x", until)

	def test_unknown_zone_is_dropped_and_clear_works(self):
		self.assertEqual(ophice.set_status("brb", tz="Mars/Base")["tz"], "")
		self.assertIsNone(ophice.set_status(""))
		self.assertIsNone(ophice.get_space()["me"]["status"])

	def test_away_chip_stays_on_the_map_when_offline(self):
		ophice.save_my_position(4, 5)
		ophice.set_status("away", "Lunch", self._in(hours=1))
		frappe.set_user("Administrator")
		chips = [c for c in ophice.get_space()["others"] if c["user"] == self.USER]
		self.assertEqual(len(chips), 1)
		self.assertTrue(chips[0]["offline"])
		self.assertEqual(chips[0]["status"]["note"], "Lunch")


class _OphiceRoomBase(FrappeTestCase):
	"""Two Raven users on the grid and a test Jitsi server, realtime patched out."""

	A = "ophice-a@example.com"
	B = "ophice-b@example.com"

	def setUp(self):
		frappe.set_user("Administrator")
		for email in (self.A, self.B):
			if not frappe.db.exists("User", email):
				user = frappe.get_doc(
					{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
				).insert(ignore_permissions=True)
				user.add_roles("Raven User")
		if not frappe.get_all("Raven Workspace", limit=1):
			frappe.get_doc({"doctype": "Raven Workspace", "workspace_name": "Ophice Test", "type": "Public"}).insert(
				ignore_permissions=True
			)
		self.conf = patch.dict(frappe.conf, {"ophice_jitsi_domain": None, "ophice_jitsi_domains": ["jitsi.example.org"]})
		self.conf.start()
		self.publish = patch.object(ophice.frappe, "publish_realtime")
		self.sent = self.publish.start()
		frappe.cache.delete_value(ophice.PRESENCE_CACHE_KEY)
		self._put(self.A, 1, 1)
		self._put(self.B, 30, 20)

	def tearDown(self):
		self.publish.stop()
		self.conf.stop()
		frappe.set_user("Administrator")
		frappe.cache.delete_value(ophice.PRESENCE_CACHE_KEY)
		frappe.db.rollback()

	def _put(self, user, x, y):
		frappe.cache.hset(ophice.PRESENCE_CACHE_KEY, user, {"user": user, "x": x, "y": y, "ts": ophice.time.time()})

	def _area(self, mode):
		frappe.set_user(self.A)
		return ophice.save_area("Chat test", "https://jitsi.example.org/ChatTest", 0, 0, 3, 3, chat_mode=mode)

	def _recipients(self):
		return {c.kwargs.get("user") for c in self.sent.call_args_list if c.args and c.args[0] == ophice.EVENT_AREA_MESSAGE}



class OphiceAreaChatTestCase(_OphiceRoomBase):
	"""Area chat (#2062): Saved, Not saved, Confidential; only for whoever stands in the area."""

	def test_saved_keeps_history_in_raven_and_only_people_inside_may_read(self):
		area = self._area("Saved")
		ophice.send_area_message(area, "Hello area")
		channel = frappe.db.get_value(ophice.AREA_DOCTYPE, area, "raven_channel")
		self.assertTrue(frappe.db.exists("Raven Message", {"channel_id": channel}))
		self.assertEqual([m["text"] for m in ophice.get_area_chat(area)["messages"]], ["Hello area"])
		frappe.set_user(self.B)
		with self.assertRaises(frappe.PermissionError):
			ophice.get_area_chat(area)
		# B steps in: same channel, the history is there, and B gets the next message.
		self._put(self.B, 2, 2)
		self.assertEqual(len(ophice.get_area_chat(area)["messages"]), 1)
		self.sent.reset_mock()
		ophice.send_area_message(area, "Hi")
		self.assertEqual(self._recipients(), {self.A, self.B})
		self.assertEqual(frappe.db.get_value(ophice.AREA_DOCTYPE, area, "raven_channel"), channel)

	def test_burn_deletes_the_saved_history(self):
		area = self._area("Saved")
		ophice.send_area_message(area, "secret")
		self.assertEqual(ophice.burn_area_chat(area), 1)
		self.assertEqual(ophice.get_area_chat(area)["messages"], [])

	def test_not_saved_burns_when_the_last_person_leaves(self):
		area = self._area("Not saved")
		ophice.send_area_message(area, "gone soon")
		self._put(self.B, 2, 2)
		self.assertFalse(ophice.leave_area(area))  # B is still inside
		frappe.cache.hdel(ophice.PRESENCE_CACHE_KEY, self.B)
		self.assertTrue(ophice.leave_area(area))
		channel = frappe.db.get_value(ophice.AREA_DOCTYPE, area, "raven_channel")
		self.assertFalse(frappe.db.exists("Raven Message", {"channel_id": channel}))

	def test_confidential_stores_nothing(self):
		area = self._area("Confidential")
		before = frappe.db.count("Raven Message")
		row = ophice.send_area_message(area, "off the record")
		self.assertEqual(row["text"], "off the record")
		self.assertEqual(frappe.db.count("Raven Message"), before)
		self.assertFalse(frappe.db.get_value(ophice.AREA_DOCTYPE, area, "raven_channel"))
		self.assertEqual(self._recipients(), {self.A})


class OphicePeopleTestCase(_OphiceRoomBase):
	"""People list (#2063): online first, details only for those who show them."""

	def _person(self, people, user):
		return next(p for p in people if p["user"] == user)

	def test_online_first_with_area_and_hide(self):
		self._area("Saved")  # A stands at 1,1 inside it
		frappe.set_user(self.B)
		people = ophice.get_people()["people"]
		self.assertTrue(people[0]["online"])
		self.assertEqual(self._person(people, self.A)["area"], "Chat test")
		frappe.set_user(self.A)
		ophice.set_hide_details(1)
		frappe.set_user(self.B)
		a = self._person(ophice.get_people()["people"], self.A)
		self.assertTrue(a["online"])
		self.assertTrue(a["hidden"])
		self.assertEqual(a["area"], "")

	def test_chat_options_and_new_dm(self):
		frappe.set_user(self.A)
		self.assertIsNone(ophice.get_chat_options(self.B)["dm"])
		url = ophice.start_direct_message(self.B)["url"]
		self.assertTrue(url.startswith("/raven/dm-channel/"))
		self.assertEqual(ophice.get_chat_options(self.B)["dm"]["url"], url)
		area = self._area("Saved")
		ophice.send_area_message(area, "x")
		self._put(self.B, 2, 2)
		frappe.set_user(self.B)
		ophice.get_area_chat(area)  # B joins the area's channel
		frappe.set_user(self.A)
		self.assertEqual(len(ophice.get_chat_options(self.B)["chats"]), 1)
