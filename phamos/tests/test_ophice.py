# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Ophice slice 1 (#2054): my own chip's remembered position and the dummy chips."""

import json
from unittest import skipUnless
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.api import ophice



def _read_encounter(encounter):
	"""What the session user sees of an encounter (the party check included)."""
	return ophice._encounter_payload(ophice._require_party(encounter, ("Open", "Parting")))


# Encounters, status and every room test use Raven (users, private channels); the CI site has no
# Raven, like for the Issue chat tests (test_issue_chat).
NEEDS_RAVEN = skipUnless("raven" in frappe.get_installed_apps(), "Raven is not installed")

class OphiceTestCase(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.defaults.clear_user_default(ophice.POSITION_KEY)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_spawn_when_nothing_is_stored(self):
		space = ophice.get_space()
		self.assertEqual((space["me"]["x"], space["me"]["y"]), (ophice._cols() // 2, ophice._rows() // 2))
		self.assertEqual((space["cols"], space["rows"]), (ophice._cols(), ophice._rows()))
		self.assertEqual(space["me"]["user"], "Administrator")

	def test_free_position_round_trip(self):
		ophice.save_my_position(3.456, "7.1")
		me = ophice.get_space()["me"]
		self.assertEqual((me["x"], me["y"]), (3.46, 7.1))

	def test_clamped_to_the_grid(self):
		self.assertEqual(ophice.save_my_position(-5, 999), {"x": 0.0, "y": ophice._rows() - 1.0})
		self.assertEqual(ophice.save_my_position("abc", "nan"), {"x": 0.0, "y": 0.0})

	def test_broken_stored_value_falls_back_to_spawn(self):
		# Not coming in (#2072): otherwise the chip is beamed into the site's start space.
		frappe.cache.hset(ophice.LAST_SEEN_CACHE_KEY, frappe.session.user, ophice.time.time())
		frappe.defaults.set_user_default(ophice.POSITION_KEY, "not json")
		me = ophice.get_space()["me"]
		self.assertEqual((me["x"], me["y"]), (ophice._cols() // 2, ophice._rows() // 2))

	def test_dummies_from_site_config(self):
		dummies = [{"user": "Guest", "x": 5, "y": 6}, {"user": "Administrator", "x": 1, "y": 1}, {"user": "nobody@example.com"}, "junk"]
		with patch.dict(frappe.conf, {ophice.DUMMIES_CONF_KEY: dummies}):
			others = ophice.get_space()["others"]
		# Guest is an enabled user; myself and unknown users are left out.
		# Only the dummy chips: people really online on the site are not this test's business.
		others = [o for o in others if o.get("dummy")]
		self.assertEqual([(o["user"], o["x"], o["y"]) for o in others], [("Guest", 5.0, 6.0)])

	def test_no_dummies_without_site_config(self):
		# Real away users of the site would show up too: not part of this test.
		with patch.dict(frappe.conf, {ophice.DUMMIES_CONF_KEY: None}), patch.object(ophice, "_away_offline", return_value=[]):
			# No dummy chips (people really online on the site may be there).
			self.assertEqual([o for o in ophice.get_space()["others"] if o.get("dummy")], [])

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
			self.assertEqual(ophice.move(99, -1), {"user": "Administrator", "x": ophice._cols() - 1.0, "y": 0.0})
		self.assertEqual(publish.call_args.args[0], ophice.EVENT_MOVE)

	def test_move_lift_is_passed_on(self):
		ophice.heartbeat(1, 1)
		frappe.cache.delete_value(f"phamos_ophice_moves:{frappe.session.user}")
		with patch.object(ophice.frappe, "publish_realtime"):
			self.assertNotIn("lift", ophice.move(2, 2))
			self.assertEqual(ophice.move(4, 2, lift=1)["lift"], 1)

	def test_move_throttled_per_user(self):
		ophice.heartbeat(1, 1)
		frappe.cache.delete_value(f"phamos_ophice_moves:{frappe.session.user}")
		with patch.object(ophice.frappe, "publish_realtime"):
			results = [ophice.move(2, 2) for _ in range(ophice.MOVE_LIMIT + 3)]
		self.assertTrue(all(results[: ophice.MOVE_LIMIT]))
		self.assertEqual(results[ophice.MOVE_LIMIT :], [None, None, None])

	def test_throttled_move_still_keeps_the_spot(self):
		# #2161: the server checks a chat's distance against this spot; a dropped one said "Move closer".
		ophice.heartbeat(1, 1)
		frappe.cache.delete_value(f"phamos_ophice_moves:{frappe.session.user}")
		with patch.object(ophice.frappe, "publish_realtime") as publish:
			for _ in range(ophice.MOVE_LIMIT):
				ophice.move(2, 2)
			publish.reset_mock()
			self.assertIsNone(ophice.move(7, 8))
		publish.assert_not_called()
		self.assertEqual(ophice._position_of("Administrator"), (7.0, 8.0))

	def test_reload_onto_someone_lands_next_to_them(self):
		# #2160: someone walked onto my spot while I reloaded; on top of each other we got stuck.
		frappe.cache.hset(ophice.LAST_SEEN_CACHE_KEY, frappe.session.user, ophice.time.time())
		ophice.save_my_position(10, 10)
		self._put("someone@example.com", 10.2, 10)
		with patch.dict(frappe.conf, {ophice.DUMMIES_CONF_KEY: None}):
			me = ophice.get_space()["me"]
		self.assertGreaterEqual(ophice.math.hypot(me["x"] - 10.2, me["y"] - 10), ophice.START_SPOT_GAP)
		self.assertLessEqual(ophice.math.hypot(me["x"] - 10, me["y"] - 10), 2)
		# Saved, so the next reload keeps it.
		self.assertEqual(ophice._stored_position(), {"x": me["x"], "y": me["y"]})

	def test_reload_spot_stays_out_of_spaces(self):
		# Review of !1349: the free spot must not put me into a meeting space I did not walk into.
		frappe.db.delete(ophice.AREA_DOCTYPE)
		frappe.get_doc(
			{"doctype": ophice.AREA_DOCTYPE, "title": "Room", "kind": "Meeting", "x": 9, "y": 7, "width": 6, "height": 3}
		).insert(ignore_permissions=True)
		frappe.cache.hset(ophice.LAST_SEEN_CACHE_KEY, frappe.session.user, ophice.time.time())
		ophice.save_my_position(10, 10)
		self._put("someone@example.com", 10, 10)
		with patch.dict(frappe.conf, {ophice.DUMMIES_CONF_KEY: None}):
			me = ophice.get_space()["me"]
		# The tile right above (10, 9) is free but inside the room.
		self.assertGreaterEqual(me["y"], 10)
		self.assertGreaterEqual(ophice.math.hypot(me["x"] - 10, me["y"] - 10), ophice.START_SPOT_GAP)

	def test_reload_next_to_someone_stays(self):
		frappe.cache.hset(ophice.LAST_SEEN_CACHE_KEY, frappe.session.user, ophice.time.time())
		ophice.save_my_position(10, 10)
		self._put("someone@example.com", 11, 10)
		with patch.dict(frappe.conf, {ophice.DUMMIES_CONF_KEY: None}):
			me = ophice.get_space()["me"]
		self.assertEqual((me["x"], me["y"]), (10.0, 10.0))

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


@NEEDS_RAVEN
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
		# Independent of the site's map: no encounters inside its spaces with a call (rolled back).
		frappe.db.delete(ophice.AREA_DOCTYPE)
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
			self.assertEqual(first["video"]["domain"], "meet.systemli.org")
			self.assertRegex(first["video"]["room"], r"^ophice-[0-9a-f]{24}$")
			self.assertEqual(again["video"], first["video"])
		with patch.dict(frappe.conf, {"ophice_video": 0}):
			self.assertIsNone(self._open(self.A, self.B)["video"])
		with patch.dict(frappe.conf, {"ophice_jitsi_domain": "evil.example/x?y", "ophice_video": None}):
			self.assertIsNone(self._open(self.A, self.B)["video"])

	def test_no_encounter_in_a_space_with_a_call(self):
		"""A meeting space with a Jitsi link has its own call and chat: no encounter there."""
		ophice.save_area("Call room", "https://meet.systemli.org/CallRoom", 4, 4, 2, 2)
		# Checked by its message: "Move closer to chat." is a ValidationError too.
		with self.assertRaisesRegex(frappe.ValidationError, "its own meeting"):
			self._open(self.A, self.B)
		# One of the two outside is not enough: the other one is still in the meeting.
		self._put(self.B, 6.5, 5)
		with self.assertRaisesRegex(frappe.ValidationError, "its own meeting"):
			self._open(self.B, self.A)
		frappe.set_user("Administrator")
		self._put(self.A, 7, 5)
		self._put(self.B, 8, 5)
		self.assertTrue(self._open(self.A, self.B)["encounter"])

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

	def test_other_not_on_the_map_is_said_so(self):
		# #2161: they were reloading; "Move closer to chat" sent me looking for a problem that wasn't there.
		frappe.cache.hdel(ophice.PRESENCE_CACHE_KEY, self.B)
		with self.assertRaises(frappe.ValidationError) as raised:
			self._open(self.A, self.B)
		self.assertEqual(str(raised.exception), "Not on the map right now.")

	def test_messages_reach_both_and_stay_private(self):
		encounter = self._open(self.A, self.B)["encounter"]
		with patch.object(ophice.frappe, "publish_realtime") as publish:
			row = ophice.send_encounter_message(encounter, "Hi <b>there</b>\nline 2")
		mine = [c for c in publish.call_args_list if c.args[0] == ophice.EVENT_MESSAGE]
		self.assertEqual({c.kwargs["user"] for c in mine}, {self.A, self.B})
		self.assertEqual(row["owner"], self.A)
		frappe.set_user(self.B)
		messages = _read_encounter(encounter)["messages"]
		self.assertEqual([m["owner"] for m in messages], [self.A])
		# shown as text: the tags the user typed come back as text, not markup
		self.assertEqual(messages[0]["text"], "Hi <b>there</b>\nline 2")
		frappe.set_user(self.C)
		with self.assertRaises(frappe.PermissionError):
			_read_encounter(encounter)
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
			messages = _read_encounter(encounter)["messages"]
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

	def test_parting_waits_for_the_other_page(self):
		# #2161: both pages part at the same moment. The other one burns the empty chat while this
		# one waits for the pair's lock; this one then finds it gone instead of failing the delete.
		encounter = self._open(self.A, self.B)["encounter"]
		doc = frappe.db.get_value("Ophice Encounter", encounter, ophice.ENCOUNTER_FIELDS, as_dict=True)
		lock = ophice._lock_pair
		locked = []

		def other_page_first(pair_key):
			locked.append(pair_key)
			ophice._burn(doc, silent=True)
			lock(pair_key)

		with patch.object(ophice, "_lock_pair", side_effect=other_page_first):
			self.assertIsNone(ophice.part_encounter(encounter))
		self.assertEqual(locked, [ophice._pair_key(self.A, self.B)])
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

	def test_leaving_locks_pairs_in_one_order(self):
		# Review of !1349: a request locking several pairs takes them sorted by pair key, so two
		# such requests never wait for each other in a circle. A–C is the newer chat, so the
		# list comes newest first (A–C before A–B) unless it is sorted.
		self._put(self.C, 5, 6)
		self._open(self.A, self.B)
		frappe.db.sql("UPDATE `tabOphice Encounter` SET modified = modified - INTERVAL 1 MINUTE")
		self._open(self.A, self.C)
		lock = ophice._lock_pair
		locked = []

		def record(pair_key):
			locked.append(pair_key)
			lock(pair_key)

		with patch.object(ophice, "_lock_pair", side_effect=record), patch.object(ophice.frappe, "publish_realtime"):
			ophice._part_all_mine(self.A)
		self.assertEqual(locked, [ophice._pair_key(self.A, self.B), ophice._pair_key(self.A, self.C)])

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


	def test_background_layout_in_tiles_is_clamped_and_shared(self):
		"""#2089: place and width in grid tiles, may reach beyond the grid, clamped; ratio stored."""
		cols, rows = ophice._grid()
		with patch.object(ophice.frappe, "publish_realtime"):
			with self.assertRaises(frappe.ValidationError):
				ophice.set_background_layout(0, 1, 1, 30)  # no background yet
			ophice._store_background(self._png(), "map.png")
			self.assertEqual(ophice.get_space()["background_layout"], {"fit": True, "left": 0, "top": 0, "width": cols, "zoom": 1.0})
			ratio = ophice.get_space()["background_ratio"]
			self.assertGreater(ratio, 0)
			layout = ophice.set_background_layout(0, -999, 3.25, 999, 9)
		self.assertEqual(layout["width"], 4 * cols)
		self.assertEqual(layout["left"], -4 * cols)
		self.assertEqual((layout["top"], layout["zoom"], layout["fit"]), (3.25, 3.0, False))
		self.assertEqual(ophice.get_space()["background_layout"], layout)

	def test_old_percent_layout_converts_to_tiles(self):
		with patch.object(ophice.frappe, "publish_realtime"):
			ophice._store_background(self._png(), "map.png")
		cols, rows = ophice._grid()
		value = ophice._background()
		value["layout"] = {"fit": False, "scale": 50, "x": 100, "y": 0}
		layout = ophice._background_layout(value)
		# Half the grid wide, flush right, at the top.
		self.assertEqual((layout["width"], layout["left"], layout["top"]), (cols / 2, cols / 2, 0))


class OphiceAreaTestCase(FrappeTestCase):
	"""Meeting areas (#2060): rectangles with a fixed Jitsi meeting."""

	def setUp(self):
		frappe.set_user("Administrator")
		self.conf = patch.dict(frappe.conf, {"ophice_jitsi_domain": None, "ophice_jitsi_domains": ["jitsi.example.org"]})
		self.conf.start()
		self.publish = patch.object(ophice.frappe, "publish_realtime")
		self.publish.start()
		# The default grid (#2089); the site's own size comes back with the rollback.
		frappe.db.set_default(ophice.GRID_KEY, json.dumps({"cols": ophice.COLS, "rows": ophice.ROWS}))

	def tearDown(self):
		self.publish.stop()
		self.conf.stop()
		frappe.db.rollback()

	def test_save_reads_the_room_from_the_url_and_shows_in_the_space(self):
		name = ophice.save_area("Standup", " https://meet.systemli.org/FullTimeDefencesRejectOverly ", 2, 3, 4, 2)
		area = next(a for a in ophice.get_space()["areas"] if a.name == name)
		self.assertEqual((area.jitsi_domain, area.jitsi_room), ("meet.systemli.org", "FullTimeDefencesRejectOverly"))
		self.assertEqual((area.x, area.y, area.width, area.height), (2, 3, 4, 2))
		self.assertEqual(area.meeting_url, "https://meet.systemli.org/FullTimeDefencesRejectOverly")

	def test_an_old_meet_jit_si_link_keeps_its_room_on_the_site_server(self):
		"""#2108: meet.jit.si links still work; only the server changes."""
		name = ophice.save_area("Old link", "https://meet.jit.si/OurStandup", 2, 3, 4, 2)
		area = frappe.get_doc("Ophice Area", name)
		self.assertEqual((area.jitsi_domain, area.jitsi_room), ("meet.systemli.org", "OurStandup"))
		self.assertEqual(area.meeting_url, "https://meet.systemli.org/OurStandup")

	def test_patch_moves_areas_from_meet_jit_si_and_keeps_the_room(self):
		"""#2108: existing areas on meet.jit.si move to the site's server, the room stays."""
		from phamos.patches.v1_0 import ophice_areas_to_site_jitsi_server

		# Room on the map for two areas; the site's own areas come back with the rollback.
		frappe.db.delete("Ophice Area")
		old = ophice.save_area("Before", "https://jitsi.example.org/KeptRoom", 2, 3, 4, 2)
		other = ophice.save_area("Elsewhere", "https://jitsi.example.org/OtherRoom", 10, 3, 4, 2)
		frappe.db.set_value(
			"Ophice Area", old, {"jitsi_domain": "meet.jit.si", "meeting_url": "https://meet.jit.si/KeptRoom"}
		)
		ophice_areas_to_site_jitsi_server.execute()
		moved = frappe.get_doc("Ophice Area", old)
		self.assertEqual((moved.jitsi_domain, moved.jitsi_room), ("meet.systemli.org", "KeptRoom"))
		self.assertEqual(moved.meeting_url, "https://meet.systemli.org/KeptRoom")
		# Another allowed server is left alone.
		self.assertEqual(frappe.db.get_value("Ophice Area", other, "jitsi_domain"), "jitsi.example.org")

	def test_patch_leaves_meet_jit_si_where_the_site_allows_it(self):
		from phamos.patches.v1_0 import ophice_areas_to_site_jitsi_server

		name = ophice.save_area("Kept", "https://jitsi.example.org/StayRoom", 2, 3, 4, 2)
		frappe.db.set_value("Ophice Area", name, "jitsi_domain", "meet.jit.si")
		with patch.dict(frappe.conf, {"ophice_jitsi_domain": "meet.jit.si"}):
			ophice_areas_to_site_jitsi_server.execute()
		self.assertEqual(frappe.db.get_value("Ophice Area", name, "jitsi_domain"), "meet.jit.si")

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
		# Independent of the spaces on the site's map (rolled back in tearDown).
		frappe.db.delete(ophice.AREA_DOCTYPE)
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

	def test_areas_snap_to_half_tiles(self):
		"""#2067: the grid for areas has double the resolution."""
		frappe.set_user("Administrator")
		name = ophice.save_area("Half", "https://jitsi.example.org/Half", 2.3, 4.74, 1.26, 0.1)
		area = frappe.get_doc(ophice.AREA_DOCTYPE, name)
		self.assertEqual((area.x, area.y, area.width, area.height), (2.5, 4.5, 1.5, 0.5))


@NEEDS_RAVEN
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


@NEEDS_RAVEN
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
		# A may change the map (#2071); B may not.
		frappe.get_doc("User", self.A).add_roles(ophice.MAP_EDITOR_ROLE)
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
	"""Area chat (#2062, #2066): batches per meeting, grace time, Keep/Burn vote; Confidential stores nothing."""

	def _meeting(self, mode, text="Hello area", area=None):
		"""A and B in one area, A wrote a message: the running batch."""
		area = area or self._area(mode)
		self._put(self.A, 1, 1)
		self._put(self.B, 2, 2)
		frappe.set_user(self.A)
		ophice.send_area_message(area, text)
		return area, frappe.get_doc(ophice.BATCH_DOCTYPE, ophice._running_batch_name(area))

	def _empty(self, area):
		"""Both walk out: B's tab is gone, A leaves."""
		frappe.cache.hdel(ophice.PRESENCE_CACHE_KEY, self.B)
		frappe.set_user(self.A)
		self.assertTrue(ophice.leave_area(area))
		frappe.cache.hdel(ophice.PRESENCE_CACHE_KEY, self.A)

	def _grace_over(self, batch):
		frappe.db.set_value(ophice.BATCH_DOCTYPE, batch.name, "grace_until", ophice.add_to_date(ophice.now_datetime(), minutes=-1))
		ophice._settle_batches()

	def test_batch_has_everyone_inside_and_only_people_inside_may_read(self):
		area = self._area("Saved")
		frappe.set_user(self.B)
		with self.assertRaises(frappe.PermissionError):
			ophice.get_area_chat(area)
		self._put(self.B, 2, 2)
		chat = ophice.get_area_chat(area)
		self.assertEqual(len(chat["batches"]), 1)
		self.assertEqual(set(chat["batches"][0]["participants"]), {self.A, self.B})
		self.sent.reset_mock()
		ophice.send_area_message(area, "Hi")
		self.assertEqual(self._recipients(), {self.A, self.B})
		channel = frappe.db.get_value(ophice.BATCH_DOCTYPE, chat["batches"][0]["name"], "raven_channel")
		self.assertTrue(frappe.db.exists("Raven Message", {"channel_id": channel}))

	def test_grace_time_continues_the_batch_and_saved_mode_keeps_it(self):
		area, batch = self._meeting("Saved")
		self._empty(area)
		self.assertEqual(frappe.db.get_value(ophice.BATCH_DOCTYPE, batch.name, "status"), "Ending")
		# A's connection is back within the grace time: the same batch carries on.
		self._put(self.A, 1, 1)
		frappe.set_user(self.A)
		self._put(self.B, 2, 2)
		ophice.get_area_chat(area)
		self.assertEqual(frappe.db.get_value(ophice.BATCH_DOCTYPE, batch.name, "status"), "Open")
		self._empty(area)
		self._grace_over(batch)
		self.assertEqual(frappe.db.get_value(ophice.BATCH_DOCTYPE, batch.name, "status"), "Kept")
		# The next meeting starts a new batch; the old history is there.
		self._put(self.A, 1, 1)
		self._put(self.B, 2, 2)
		frappe.set_user(self.A)
		self.assertEqual([b["status"] for b in ophice.get_area_chat(area)["batches"]], ["Kept", "Open"])

	def test_not_saved_deletes_after_grace_unless_saved(self):
		area, batch = self._meeting("Not saved")
		channel = batch.raven_channel
		self._empty(area)
		frappe.set_user(self.B)
		self.assertEqual([n["name"] for n in ophice.get_batch_notices()], [batch.name])
		self._grace_over(batch)
		self.assertFalse(frappe.db.exists(ophice.BATCH_DOCTYPE, batch.name))
		self.assertFalse(frappe.db.exists("Raven Channel", channel))
		self.assertFalse(frappe.db.exists("Raven Message", {"channel_id": channel}))
		# Saved by one person during the grace time: kept.
		area2, batch2 = self._meeting("Not saved", area=area)
		self._empty(area2)
		frappe.set_user(self.B)
		self.assertEqual(ophice.vote_batch(batch2.name, "Keep")["result"], "voting")
		self._grace_over(batch2)
		self.assertEqual(frappe.db.get_value(ophice.BATCH_DOCTYPE, batch2.name, "status"), "Kept")

	def test_vote_majority_burns_and_a_tie_keeps(self):
		area, batch = self._meeting("Saved")
		with self.assertRaises(frappe.PermissionError):
			frappe.set_user("Administrator")
			ophice.vote_batch(batch.name, "Burn")
		frappe.set_user(self.A)
		self.assertEqual(ophice.vote_batch(batch.name, "Burn")["result"], "voting")
		frappe.set_user(self.B)
		self.assertEqual([n["name"] for n in ophice.get_batch_notices()], [batch.name])
		self.assertEqual(ophice.vote_batch(batch.name, "Keep")["result"], "kept")  # 1:1
		self.assertTrue(frappe.db.exists(ophice.BATCH_DOCTYPE, batch.name))
		self.assertFalse(frappe.db.get_value(ophice.BATCH_DOCTYPE, batch.name, "vote_until"))
		ophice.vote_batch(batch.name, "Burn")
		frappe.set_user(self.A)
		self.assertEqual(ophice.vote_batch(batch.name, "Burn")["result"], "burned")
		self.assertFalse(frappe.db.exists(ophice.BATCH_DOCTYPE, batch.name))

	def test_notices_only_when_there_is_something_to_decide(self):
		"""#2091: a kept chat, or one without messages, is no notice."""
		area, batch = self._meeting("Saved")
		self._empty(area)
		frappe.set_user(self.B)
		self.assertEqual(ophice.get_batch_notices(), [])  # kept anyway after the grace time
		frappe.set_user(self.A)
		ophice.save_area("Chat test", "https://jitsi.example.org/ChatTest", 0, 0, 3, 3, name=area, chat_mode="Not saved")
		frappe.set_user(self.B)
		self.assertEqual([n["name"] for n in ophice.get_batch_notices()], [batch.name])
		for message in frappe.get_all("Raven Message", filters={"channel_id": batch.raven_channel}, pluck="name"):
			frappe.delete_doc("Raven Message", message, ignore_permissions=True, force=True)
		self.assertEqual(ophice.get_batch_notices(), [])  # nothing to save

	def test_vote_window_ends_with_the_votes_cast(self):
		area, batch = self._meeting("Saved")
		frappe.set_user(self.A)
		ophice.vote_batch(batch.name, "Burn")
		frappe.db.set_value(ophice.BATCH_DOCTYPE, batch.name, "vote_until", ophice.add_to_date(ophice.now_datetime(), minutes=-1))
		ophice._settle_batches()
		self.assertFalse(frappe.db.exists(ophice.BATCH_DOCTYPE, batch.name))

	def test_timeline_shows_who_joined_and_left(self):
		area, batch = self._meeting("Saved")
		# B walks out while A stays.
		frappe.cache.hdel(ophice.PRESENCE_CACHE_KEY, self.B)
		frappe.set_user(self.B)
		self.assertFalse(ophice.leave_area(area))
		frappe.set_user(self.A)
		timeline = ophice.get_area_chat(area)["batches"][0]["timeline"]
		self.assertEqual(
			[(t["type"], t.get("user") or t.get("owner"), t.get("event")) for t in timeline],
			[("event", self.A, "Joined"), ("event", self.B, "Joined"), ("message", self.A, None), ("event", self.B, "Left")],
		)
		self.assertTrue(all("at_in" in t for t in timeline))

	def test_confidential_stores_nothing(self):
		area = self._area("Confidential")
		before = frappe.db.count("Raven Message")
		row = ophice.send_area_message(area, "off the record")
		self.assertEqual(row["text"], "off the record")
		self.assertEqual(frappe.db.count("Raven Message"), before)
		self.assertFalse(frappe.db.exists(ophice.BATCH_DOCTYPE, {"area": area}))
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


class OphiceWorkingOnTestCase(FrappeTestCase):
	"""What someone works on (#2064): the running timer's Implementation, not the task."""

	def setUp(self):
		from phamos.phamos.doctype.stakeholder_meeting.test_stakeholder_meeting import make_implementation
		from phamos.tests.test_personal_checkin import _ensure_employee, _ensure_user

		for target in ("frappe.db.commit", "frappe.desk.form.assign_to.notify_assignment"):
			patcher = patch(target)
			patcher.start()
			self.addCleanup(patcher.stop)
		frappe.set_user("Administrator")
		self.user = "tm-a@example.com"
		_ensure_user(self.user)
		employee = _ensure_employee(self.user)
		activity = "TM Development"
		if not frappe.db.exists("Activity Type", activity):
			frappe.get_doc({"doctype": "Activity Type", "activity_type": activity}).insert(ignore_permissions=True)
		frappe.db.set_value("Employee", employee, "activity_type", activity)
		self.implementation = make_implementation().name
		self.project = frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": "Ophice working on",
				"status": "Open",
				"task_in_timesheet_record": "Task is optional",
				"percent_billable": "75",
				"custom_implementation": self.implementation,
				# Mandatory custom field (phamos/phamos/custom/project.json); enforced on version-15.
				"project_owner": "Administrator",
			}
		).insert(ignore_permissions=True).name

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_running_timer_shows_the_implementation_without_goal(self):
		from phamos.api import personal_cockpit as pc

		self.assertEqual(ophice._working_on([self.user]), {})
		frappe.set_user(self.user)
		pc.start_timer(self.project, 3600, "Private goal text")
		frappe.set_user("Administrator")
		card = ophice._working_on([self.user])[self.user]
		self.assertEqual(card["implementation"], self.implementation)
		self.assertEqual(card["project_name"], "Ophice working on")
		self.assertTrue(card["url"].startswith("/app/implementation/"))
		self.assertNotIn("Private goal text", str(card))


class OphiceCockpitTestCase(_OphiceRoomBase):
	"""The cockpit someone is in (#2065): live only, never for those who hide their details."""

	def tearDown(self):
		frappe.cache.hdel(ophice.COCKPIT_CACHE_KEY, self.A)
		super().tearDown()

	def test_heartbeat_shows_the_cockpit_icon(self):
		frappe.set_user(self.A)
		self.assertFalse(ophice.cockpit_heartbeat("/not-a-cockpit"))
		self.assertTrue(ophice.cockpit_heartbeat("/sales-cockpit"))
		frappe.set_user(self.B)
		a = next(p for p in ophice.get_people()["people"] if p["user"] == self.A)
		self.assertEqual(a["cockpit"]["route"], "/sales-cockpit")
		self.assertTrue(a["cockpit"]["logo"])
		frappe.set_user(self.A)
		ophice.set_hide_details(1)
		self.assertFalse(ophice.cockpit_heartbeat("/sales-cockpit"))
		frappe.set_user(self.B)
		a = next(p for p in ophice.get_people()["people"] if p["user"] == self.A)
		self.assertIsNone(a["cockpit"])


def _tiny_png():
	from io import BytesIO

	from PIL import Image

	buffer = BytesIO()
	Image.new("RGB", (4, 4), "green").save(buffer, format="PNG")
	return buffer.getvalue()


class OphiceAppTestCase(FrappeTestCase):
	"""Ophice as an app of its own (#2070): on the Apps screen and at /ophice for System Users."""

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_app_permission_and_route(self):
		from phamos.hooks import add_to_apps_screen, website_route_rules

		tile = next(t for t in add_to_apps_screen if t["name"] == "ophice")
		self.assertEqual(tile["route"], "/ophice")
		self.assertIn({"from_route": "/ophice", "to_route": "ophice"}, website_route_rules)
		frappe.set_user("Administrator")
		self.assertTrue(ophice.check_app_permission())
		# Exactly one of the two Ophice tiles shows (start page or not).
		self.assertNotEqual(ophice.check_start_tile_permission(), ophice.check_tile_permission())
		frappe.set_user("Guest")
		self.assertFalse(ophice.check_app_permission())


class OphiceMapEditorTestCase(_OphiceRoomBase):
	"""Map editor role (#2071): only map editors change spaces and the background."""

	def test_only_map_editors_change_the_map(self):
		area = self._area("Saved")  # A is a map editor
		frappe.set_user(self.A)
		self.assertTrue(ophice.get_space()["can_edit_map"])
		frappe.set_user(self.B)
		self.assertFalse(ophice.get_space()["can_edit_map"])
		with self.assertRaises(frappe.PermissionError):
			ophice.save_area("Mine", "https://jitsi.example.org/Mine", 10, 10, 2, 2)
		with self.assertRaises(frappe.PermissionError):
			ophice.delete_area(area)
		with self.assertRaises(frappe.PermissionError):
			ophice.set_background_layout(fit=0, width=20)
		with self.assertRaises(frappe.PermissionError):
			ophice.remove_background()
		self.assertTrue(frappe.db.exists(ophice.AREA_DOCTYPE, area))


class OphiceStartSpaceTestCase(_OphiceRoomBase):
	"""Start space and beam-in (#2072): coming in lands you in the start space, a reload does not."""

	def setUp(self):
		super().setUp()
		frappe.cache.hdel(ophice.LAST_SEEN_CACHE_KEY, self.A)
		# Independent of the spaces on the site's map; the rollback in tearDown brings them back.
		frappe.db.delete(ophice.AREA_DOCTYPE)
		frappe.set_user(self.A)
		self.start = ophice.save_area("Entrance", "", 20, 10, 3, 2, kind="Start")

	def tearDown(self):
		frappe.cache.hdel(ophice.LAST_SEEN_CACHE_KEY, self.A)
		frappe.cache.delete_value(ophice._beam_key(self.A))
		super().tearDown()

	def _inside_start(self, me):
		return 20 <= me["x"] and me["x"] + 1 <= 23 and 10 <= me["y"] and me["y"] + 1 <= 12

	def test_only_one_start_space_without_meeting_or_chat(self):
		self.assertEqual(frappe.db.get_value(ophice.AREA_DOCTYPE, self.start, "meeting_url"), "")
		with self.assertRaises(frappe.ValidationError):
			ophice.save_area("Second", "", 2, 2, 2, 2, kind="Start")
		with self.assertRaises(frappe.ValidationError):
			ophice.get_area_chat(self.start)

	def test_coming_in_beams_into_the_start_space_and_a_reload_does_not(self):
		first = ophice.get_space()
		self.assertTrue(first["beam_in"])
		self.assertTrue(self._inside_start(first["me"]))
		# The first heartbeat tells the others to play the beam-in, once.
		ophice.heartbeat(first["me"]["x"], first["me"]["y"])
		ophice.heartbeat(first["me"]["x"], first["me"]["y"])
		beams = [
			c.args[1].get("beam")
			for c in self.sent.call_args_list
			if c.args and c.args[0] == ophice.EVENT_PRESENCE and c.args[1].get("user") == self.A
		]
		self.assertEqual(beams, [True, None])
		# Moved away, a second tab while the chip is on the map: no beam-in, same spot.
		ophice.save_my_position(5, 5)
		again = ophice.get_space()
		self.assertFalse(again["beam_in"])
		self.assertEqual((again["me"]["x"], again["me"]["y"]), (5.0, 5.0))
		# Reloaded right after a step (the page left first, with its spot; the delayed save had not
		# gone out yet): beamed in again, at the spot it stood on (PM, 2026-11-22, 2026-11-23).
		ophice.leave(6, 5)
		reload = ophice.get_space()
		self.assertTrue(reload["beam_in"])
		self.assertEqual((reload["me"]["x"], reload["me"]["y"]), (6.0, 5.0))
		self.assertTrue(ophice.heartbeat(5, 5).get("beam"))
		# The chip dropped off the map (laptop asleep): the next heartbeat beams it in.
		frappe.cache.hdel(ophice.PRESENCE_CACHE_KEY, self.A)
		self.assertTrue(ophice.heartbeat(5, 5).get("beam"))
		self.assertFalse(ophice.heartbeat(5, 5).get("beam"))
		# Back after more than five minutes: beamed in again.
		frappe.cache.hset(ophice.LAST_SEEN_CACHE_KEY, self.A, ophice.time.time() - ophice.ARRIVAL_GAP_SECONDS - 5)
		self.assertTrue(ophice.get_space()["beam_in"])

	def test_arrivals_do_not_land_on_each_other(self):
		self._put(self.B, 20, 10)
		for _ in range(5):
			frappe.cache.hdel(ophice.LAST_SEEN_CACHE_KEY, self.A)
			me = ophice.get_space()["me"]
			self.assertGreaterEqual(ophice.math.hypot(me["x"] - 20, me["y"] - 10), ophice.START_SPOT_GAP)


class OphiceMeetingPinTestCase(_OphiceRoomBase):
	"""Meeting points (PM, 2026-11-22): a pin for me and the people I chose, one per setter."""

	def tearDown(self):
		frappe.cache.delete_value(ophice.PIN_CACHE_KEY)
		for user in (self.A, self.B):
			frappe.cache.delete_value(ophice._pin_wait_key(user))
		super().tearDown()

	def _sent_to(self, event):
		return [c.kwargs.get("user") for c in self.sent.call_args_list if c.args and c.args[0] == event]

	def test_pin_reaches_the_chosen_people_and_replaces_my_last(self):
		frappe.set_user(self.A)
		pin = ophice.set_meeting_pin([self.B, "Guest", "nobody@example.com"], 7, 8)
		self.assertEqual(pin["users"], [self.A, self.B])
		self.assertEqual((pin["x"], pin["y"]), (7.0, 8.0))
		self.assertEqual(sorted(self._sent_to(ophice.EVENT_PIN)), sorted([self.A, self.B]))
		frappe.set_user(self.B)
		self.assertEqual([p["by"] for p in ophice.get_space()["pins"]], [self.A])
		# Right away again: wait a moment (each pin notifies everyone in it; AI review of !1303).
		frappe.set_user(self.A)
		with self.assertRaises(frappe.ValidationError):
			ophice.set_meeting_pin([self.B], 3, 3)
		# A new one replaces the old one; removing it tells everyone.
		frappe.cache.delete_value(ophice._pin_wait_key(self.A))
		ophice.set_meeting_pin([self.B], 3, 3)
		self.assertEqual(len(ophice._pins()), 1)
		ophice.remove_meeting_pin()
		self.assertEqual(ophice._pins(), {})
		self.assertIn(self.B, self._sent_to(ophice.EVENT_PIN_REMOVED))

	def test_pin_needs_someone_and_expires(self):
		frappe.set_user(self.A)
		with self.assertRaises(frappe.ValidationError):
			ophice.set_meeting_pin([self.A], 1, 1)
		ophice.set_meeting_pin([self.B], 1, 1)
		frappe.cache.hset(ophice.PIN_CACHE_KEY, self.A, {**frappe.cache.hget(ophice.PIN_CACHE_KEY, self.A), "until": 1})
		frappe.set_user(self.B)
		self.assertEqual(ophice.get_space()["pins"], [])


class OphiceCockpitBarTestCase(FrappeTestCase):
	"""Shortcut bar (#2073): the cockpits I may open, with icons, Personal Cockpit first."""

	def test_personal_cockpit_first_with_logos(self):
		frappe.set_user("Administrator")
		cockpits = ophice.get_cockpits()
		self.assertEqual(cockpits[0]["route"], "/personal-cockpit")
		self.assertTrue(all(c["logo"].startswith("/assets/phamos/manifest/") for c in cockpits))
		self.assertNotIn("/ophice", [c["route"] for c in cockpits])


class OphiceGuestAreaTestCase(_OphiceRoomBase):
	"""Guest and customer meeting areas (#2081): one guest area, any number of customer meeting
	areas, both with a meeting; for employees they work like meeting spaces."""

	def setUp(self):
		super().setUp()
		# Independent of the spaces on the site's map; the rollback in tearDown brings them back.
		frappe.db.delete(ophice.AREA_DOCTYPE)
		frappe.set_user(self.A)

	def test_one_guest_area_and_many_customer_meeting_areas(self):
		guest = ophice.save_area("Lobby", "https://jitsi.example.org/Lobby", 0, 0, 4, 3, kind="Guest")
		with self.assertRaises(frappe.ValidationError):
			ophice.save_area("Second lobby", "https://jitsi.example.org/Lobby2", 10, 0, 2, 2, kind="Guest")
		# Changing the guest area itself is fine.
		ophice.save_area("Lobby", "https://jitsi.example.org/Lobby", 0, 0, 5, 3, name=guest, kind="Guest")
		ophice.save_area("Room 1", "https://jitsi.example.org/Room1", 10, 0, 2, 2, kind="Customer meeting")
		ophice.save_area("Room 2", "https://jitsi.example.org/Room2", 13, 0, 2, 2, kind="Customer meeting")
		kinds = sorted(a.kind for a in ophice._areas())
		self.assertEqual(kinds, ["Customer meeting", "Customer meeting", "Guest"])

	def test_they_need_a_meeting_and_show_where_people_are(self):
		with self.assertRaises(frappe.ValidationError):
			ophice.save_area("No link", "", 0, 0, 2, 2, kind="Customer meeting")
		ophice.save_area("Lobby", "https://jitsi.example.org/Lobby", 0, 0, 4, 3, kind="Guest")
		frappe.set_user(self.B)
		a = next(p for p in ophice.get_people()["people"] if p["user"] == self.A)
		self.assertEqual(a["area"], "Lobby")  # A stands at 1,1


class _OphiceGuestBase(_OphiceRoomBase):
	"""A guest area and a clean guest session store; the helpers to come in as a guest."""

	def setUp(self):
		super().setUp()
		from phamos.api import ophice_guest

		self.g = ophice_guest
		frappe.db.delete(ophice.AREA_DOCTYPE)
		frappe.set_user(self.A)
		ophice.save_area("Lobby", "https://jitsi.example.org/Lobby", 10, 10, 4, 3, kind="Guest")
		frappe.set_user("Guest")
		frappe.local.ophice_guest_token = None

	# Only the sessions these tests made: real guests on the site stay in (PM tests as a guest).
	TEST_GUESTS = ("Ada Guest", "Bob Guest")

	def tearDown(self):
		frappe.local.ophice_guest_token = None
		for guest_id, entry in (frappe.cache.hgetall(self.g.GUEST_CACHE_KEY) or {}).items():
			if isinstance(entry, dict) and entry.get("name") in self.TEST_GUESTS:
				guest_id = frappe.safe_decode(guest_id)
				frappe.cache.hdel(self.g.GUEST_CACHE_KEY, guest_id)
				frappe.cache.hdel(self.g.INVITE_CACHE_KEY, guest_id)
				frappe.cache.hdel(ophice.PRESENCE_CACHE_KEY, self.g.GUEST_PREFIX + guest_id)
		super().tearDown()

	def _check(self):
		check = self.g.start_check()
		path = [[i / 10 * check["door"], i * 120] for i in range(11)]
		return check, path

	def _enter(self, name="Ada Guest"):
		check, path = self._check()
		# A person takes a moment; the test does not wait for it.
		with patch.object(self.g, "CHECK_MIN_SECONDS", 0):
			return self.g.enter(name, check["challenge"], check["door"], json.dumps(path))



class OphiceGuestEntryTestCase(_OphiceGuestBase):
	"""Guest entry (#2082): human check, a session without an account, only inside the guest area,
	only the chips there; employees see "guest" chips and list rows."""

	def test_the_human_check(self):
		check, path = self._check()  # too fast
		with self.assertRaises(frappe.ValidationError):
			self.g.enter("Ada Guest", check["challenge"], check["door"], json.dumps(path))
		with patch.object(self.g, "CHECK_MIN_SECONDS", 0):
			check, path = self._check()
			with self.assertRaises(frappe.ValidationError):  # not at the entrance
				away = check["door"] + 0.3 if check["door"] < 0.5 else check["door"] - 0.3
				self.g.enter("Ada Guest", check["challenge"], away, json.dumps(path))
			with self.assertRaises(frappe.ValidationError):  # used once already
				self.g.enter("Ada Guest", check["challenge"], check["door"], json.dumps(path))
			check, _path = self._check()
			with self.assertRaises(frappe.ValidationError):  # set, not dragged
				self.g.enter("Ada Guest", check["challenge"], check["door"], json.dumps([[check["door"], 0]]))
		with self.assertRaises(frappe.PermissionError):
			self.g.guest_space()  # no session yet

	def test_inside_the_guest_area_only_and_seeing_only_it(self):
		space = self._enter()
		me = space["me"]
		self.assertTrue(me["guest"] and me["user"].startswith("guest:"))
		self.assertTrue(10 <= me["x"] + 0.5 <= 14 and 10 <= me["y"] + 0.5 <= 13)
		moved = self.g.guest_move(0, 0)
		self.assertEqual((moved["x"], moved["y"]), (9.5, 9.5))  # stopped at the corner
		# A stands far away, B inside the guest area.
		self._put(self.B, 11, 11)
		users = {c["user"] for c in self.g.guest_space()["others"]}
		# Employees appear under an opaque id, never their user id (their e-mail address).
		self.assertEqual(users, {self.g.public_id(self.B)})
		self.assertNotIn("@", "".join(users))

	def test_employees_see_the_guest(self):
		self._enter("Ada Guest")
		frappe.set_user(self.A)
		row = ophice.get_people()["people"][0]
		self.assertTrue(row["guest"])
		self.assertEqual((row["full_name"], row["area"]), ("Ada Guest", "Lobby"))
		chips = [c for c in ophice.get_space()["others"] if c.get("guest")]
		self.assertEqual(len(chips), 1)

	def test_no_guest_area_no_entry(self):
		frappe.db.delete(ophice.AREA_DOCTYPE)
		with self.assertRaises(frappe.ValidationError):
			self._enter()


class OphiceGuestChatTestCase(_OphiceGuestBase):
	"""Guest chat (#2083): guests and employees in the guest area write to each other; only in
	Redis, with an expiry; employees outside the area cannot read it."""

	def tearDown(self):
		for area in ophice._areas():
			frappe.cache.delete(frappe.cache.make_key(self.g.CHAT_KEY_PREFIX + area.name))
		super().tearDown()

	def test_guest_and_employee_chat_in_the_guest_area(self):
		space = self._enter("Ada Guest")
		area = space["areas"][0]["name"]
		self.assertEqual(space["room"]["jitsi_room"], "Lobby")
		self._put(self.B, 11, 11)  # B stands in the guest area, A far away
		self.sent.reset_mock()
		self.g.guest_send("Hello, is anyone there?")
		told = {c.kwargs.get("user") for c in self.sent.call_args_list if c.args and c.args[0] == self.g.EVENT_GUEST_CHAT}
		self.assertEqual(told, {self.B})
		frappe.set_user(self.B)
		self.g.send_guest_chat(area, "Welcome, Ada!")
		messages = self.g.get_guest_chat(area)["messages"]
		self.assertEqual([(m["author"], m["guest"]) for m in messages], [("Ada Guest", True), ("ophice-b", False)])
		# Only in Redis, and it runs out when nobody keeps it alive.
		key = frappe.cache.make_key(self.g.CHAT_KEY_PREFIX + area)
		self.assertTrue(0 < frappe.cache.ttl(key) <= self.g.CHAT_TTL)
		self.assertFalse(frappe.db.exists("Raven Message", {"text": ("like", "%Welcome, Ada%")}))
		# The guest sees it with the next poll.
		frappe.set_user("Guest")
		self.assertEqual(len(self.g.guest_space()["room"]["messages"]), 2)

	def test_employees_outside_the_area_cannot_read_it(self):
		space = self._enter()
		frappe.set_user(self.A)  # A stands at 1,1, outside
		with self.assertRaises(frappe.PermissionError):
			self.g.get_guest_chat(space["areas"][0]["name"])


class OphiceGuestInviteTestCase(_OphiceGuestBase):
	"""Invites (#2084): pin in a customer meeting area, accept opens a corridor for this guest only,
	arrival closes it; decline tells the inviter."""

	def setUp(self):
		super().setUp()
		frappe.set_user(self.A)
		self.room = ophice.save_area("Room 1", "https://jitsi.example.org/Room1", 20, 10, 3, 3, kind="Customer meeting")
		frappe.set_user("Guest")

	def _invite(self, guest_user):
		frappe.set_user(self.A)
		invite = self.g.invite_guest(guest_user, self.room)
		frappe.set_user("Guest")
		return invite

	def test_accept_walk_the_corridor_and_arrive(self):
		me = self._enter("Ada Guest")["me"]
		invite = self._invite(me["user"])
		self.assertEqual(invite["status"], "pending")
		# The middle of the room (20, 10, 3 x 3).
		self.assertEqual((invite["pin"]["x"], invite["pin"]["y"]), (21.0, 11.0))
		# Not accepted yet: the room is still closed.
		self.assertEqual(self.g.guest_move(16, 11)["x"], 13.5)
		accepted = self.g.answer_invite(1)
		self.assertEqual(accepted["status"], "accepted")
		told = [c for c in self.sent.call_args_list if c.args and c.args[0] == self.g.EVENT_INVITE_ANSWER]
		self.assertEqual(told[-1].kwargs.get("user"), self.A)
		# Half way along the line: allowed. Far off the line: pulled back next to it.
		start, end = accepted["corridor"]["from"], accepted["corridor"]["to"]
		mid = ((start[0] + end[0]) / 2 - 0.5, (start[1] + end[1]) / 2 - 0.5)
		moved = self.g.guest_move(*mid)
		self.assertAlmostEqual(moved["x"], round(mid[0], 2), places=1)
		off = self.g.guest_move(mid[0], mid[1] - 5)
		self.assertNotEqual((off["x"], off["y"]), (round(mid[0], 2), round(mid[1] - 5, 2)))
		# Wherever it lands: on the way, in the guest area or in the room, nowhere else.
		cx, cy = off["x"] + 0.5, off["y"] + 0.5
		on_way = self.g._onto_band(accepted["corridor"], cx, cy) == (cx, cy)
		in_rect = any(self.g._inside(a, off["x"], off["y"]) for a in self.g.allowed_areas(me["user"].removeprefix("guest:")))
		self.assertTrue(on_way or in_rect)
		# At the pin: arrived, the corridor closes, the room stays open.
		self.g.guest_move(invite["pin"]["x"], invite["pin"]["y"])
		space = self.g.guest_space()
		self.assertEqual(space["invite"]["status"], "arrived")
		self.assertEqual({a["name"] for a in space["areas"]}, {self.room, space["areas"][0]["name"]})
		self.assertEqual(space["room"]["area"], self.room)

	def test_decline_and_no_one_else_uses_the_corridor(self):
		first = self._enter("Ada Guest")["me"]
		self._invite(first["user"])
		self.g.answer_invite(1)
		first_token = frappe.local.ophice_guest_token
		# A second guest: still only the guest area.
		frappe.local.ophice_guest_token = None
		second = self._enter("Bob Guest")["me"]
		self.assertLessEqual(self.g.guest_move(16, 11)["x"], 13.5)
		# The second guest declines an invite of their own: gone, the inviter is told.
		self._invite(second["user"])
		self.assertIsNone(self.g.answer_invite(0))
		self.assertIsNone(self.g.guest_space()["invite"])
		frappe.local.ophice_guest_token = first_token
		self.assertEqual(self.g.guest_space()["invite"]["status"], "accepted")

	def test_the_map_image_is_public_for_guests(self):
		"""Guests load the background without login (PM, 2026-11-22)."""
		frappe.set_user(self.A)
		with patch.object(ophice, "_set_background") as stored:
			url = ophice._store_background(_tiny_png(), "map.png")
		self.assertTrue(url.startswith("/files/"))
		self.assertEqual(frappe.db.get_value("File", {"file_url": url}, "is_private"), 0)
		frappe.delete_doc("File", frappe.db.get_value("File", {"file_url": url}), ignore_permissions=True, force=True)
		stored.assert_called_once()

	def test_only_customer_meeting_areas(self):
		me = self._enter()["me"]
		guest_area = self.g.guest_area().name
		frappe.set_user(self.A)
		with self.assertRaises(frappe.ValidationError):
			self.g.invite_guest(me["user"], guest_area)


class OphiceBrbCountdownTestCase(_OphiceRoomBase):
	"""#2074: "I'll get back to you in 15 min" is a Be right back with a return time that counts down."""

	def test_be_right_back_with_a_time(self):
		from datetime import datetime, timedelta, timezone

		frappe.set_user(self.A)
		back = (datetime.now(timezone.utc) + timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M:%SZ")
		status = ophice.set_status("brb", "I'll get back to you", back)
		self.assertEqual((status["kind"], status["until"]), ("brb", back))
		self.assertEqual(ophice._status_of(self.A)["until"], back)
		# Without a time it stays as before; in the past or too far ahead is refused.
		self.assertEqual(ophice.set_status("brb", "")["until"], "")
		past = (datetime.now(timezone.utc) - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
		with self.assertRaises(frappe.ValidationError):
			ophice.set_status("brb", "", past)
		later = (datetime.now(timezone.utc) + timedelta(hours=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
		with self.assertRaises(frappe.ValidationError):
			ophice.set_status("brb", "", later)


class OphiceCockpitSpaceTestCase(_OphiceRoomBase):
	"""Cockpit spaces (#2076): a space belongs to a cockpit, a meeting is optional; each person can
	switch off that the cockpit opens when they stop inside."""

	def setUp(self):
		super().setUp()
		frappe.db.delete(ophice.AREA_DOCTYPE)
		frappe.set_user(self.A)

	def test_cockpit_space_needs_a_known_cockpit_and_may_skip_the_meeting(self):
		with self.assertRaises(frappe.ValidationError):
			ophice.save_area("HR", "", 0, 0, 3, 3, kind="Cockpit", cockpit="/nowhere")
		name = ophice.save_area("HR", "", 0, 0, 3, 3, kind="Cockpit", cockpit="/human-resources-cockpit")
		area = next(a for a in ophice._areas() if a.name == name)
		self.assertEqual((area.kind, area.cockpit, area.jitsi_room), ("Cockpit", "/human-resources-cockpit", ""))
		with self.assertRaises(frappe.ValidationError):
			ophice.get_area_chat(name)  # no meeting, no chat
		# With a meeting it has the area chat like a meeting space.
		ophice.save_area("HR", "https://jitsi.example.org/HumanResources", 0, 0, 3, 3, name=name, kind="Cockpit", cockpit="/human-resources-cockpit")
		self.assertEqual(ophice.get_area_chat(name)["mode"], "Saved")
		self.assertIn("/human-resources-cockpit", [c["route"] for c in ophice.cockpit_choices()])

	def test_switch_off_opening_the_cockpit(self):
		self.assertTrue(ophice.get_space()["auto_cockpit"])
		ophice.set_auto_cockpit(0)
		self.assertFalse(ophice.get_space()["auto_cockpit"])
		ophice.set_auto_cockpit(1)
		self.assertTrue(ophice.get_space()["auto_cockpit"])


class OphiceStartPageTestCase(FrappeTestCase):
	"""Ophice as the start page (#2077): the Cockpit Settings switch sets Frappe's default app, whose
	first tile must be Ophice."""

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_switch_sends_everyone_to_ophice(self):
		from frappe.apps import get_default_path

		from phamos.hooks import add_to_apps_screen

		# The default app lands on its first tile it shows: Ophice is listed first for that.
		self.assertEqual(add_to_apps_screen[0]["route"], "/ophice")
		frappe.set_user("Administrator")
		settings = frappe.get_single("Cockpit Settings")
		settings.ophice_start_page = 1
		settings.save(ignore_permissions=True)
		self.assertEqual(frappe.db.get_single_value("System Settings", "default_app"), "phamos")
		self.assertEqual(get_default_path(), "/ophice")
		settings.ophice_start_page = 0
		settings.save(ignore_permissions=True)
		self.assertFalse(frappe.db.get_single_value("System Settings", "default_app"))

	def test_switch_off_keeps_the_personal_cockpit_first(self):
		"""A site whose default app is already "phamos" must not land in Ophice after the release
		(review of the release): Ophice's first tile shows only while the switch is on."""
		from frappe.apps import get_apps, get_default_path

		frappe.set_user("Administrator")
		frappe.db.set_single_value("Cockpit Settings", "ophice_start_page", 0)
		frappe.db.set_single_value("System Settings", "default_app", "phamos")
		frappe.clear_document_cache("System Settings", "System Settings")
		# A request reads System Settings once (frappe.local); tests share one frappe.local.
		if hasattr(frappe.local, "system_settings"):
			del frappe.local.system_settings
		self.assertEqual(get_default_path(), "/personal-cockpit")
		# Ophice is still on the Apps screen, once.
		self.assertEqual([a["route"] for a in get_apps()].count("/ophice"), 1)

	def test_saving_other_settings_leaves_the_default_app_alone(self):
		frappe.set_user("Administrator")
		frappe.db.set_single_value("System Settings", "default_app", "phamos")
		settings = frappe.get_single("Cockpit Settings")
		settings.ophice_start_page = 0
		settings.personal_color = settings.personal_color or "#0e7490"
		settings.save(ignore_permissions=True)
		self.assertEqual(frappe.db.get_single_value("System Settings", "default_app", cache=False), "phamos")


class OphiceGridTestCase(_OphiceRoomBase):
	"""Growable grid (#2089): map editors set it, spaces are never cut off, chips clamp to it."""

	def test_grid_grows_and_clamps(self):
		frappe.set_user(self.A)  # map editor
		self.assertEqual(ophice.set_grid(60, 999), {"cols": 60, "rows": 80})
		self.assertEqual(ophice.get_space()["cols"], 60)
		self.assertEqual(ophice.save_my_position(59, 79), {"x": 59.0, "y": 79.0})
		frappe.set_user(self.B)
		with self.assertRaises(frappe.PermissionError):
			ophice.set_grid(30, 20)

	def test_shrinking_never_cuts_a_space_off(self):
		frappe.set_user(self.A)
		ophice.set_grid(60, 40)
		ophice.save_area("Far", "https://jitsi.example.org/FarAway", 50, 30, 4, 4)
		with self.assertRaises(frappe.ValidationError):
			ophice.set_grid(40, 25)
		self.assertEqual(ophice._grid(), (60, 40))


class OphiceGuestReviewTestCase(_OphiceGuestBase):
	"""Fixes from the review of the develop release: guest input, chat between visitors, flooding,
	clean-up, e-mail addresses."""

	def tearDown(self):
		for area in ophice._areas():
			frappe.cache.delete(frappe.cache.make_key(self.g.CHAT_KEY_PREFIX + area.name))
		super().tearDown()

	def test_not_a_number_never_reaches_the_presence_list(self):
		self._enter()
		for x, y in (("nan", "nan"), ("inf", "-inf"), ("text", None)):
			moved = self.g.guest_move(x, y)
			self.assertTrue(ophice.math.isfinite(moved["x"]) and ophice.math.isfinite(moved["y"]))
		for chip in ophice._online():
			self.assertTrue(ophice.math.isfinite(chip["x"]) and ophice.math.isfinite(chip["y"]))

	def test_a_later_guest_does_not_read_an_earlier_conversation(self):
		self._enter("Ada Guest")
		self.g.guest_send("Our offer is 10 000 EUR")
		ada = frappe.local.ophice_guest_token
		frappe.local.ophice_guest_token = None
		self._enter("Bob Guest")
		self.assertEqual(self.g.guest_space()["room"]["messages"], [])
		self.g.guest_send("Hello")
		self.assertEqual([m["text"] for m in self.g.guest_space()["room"]["messages"]], ["Hello"])
		frappe.local.ophice_guest_token = ada
		self.assertEqual(len(self.g.guest_space()["room"]["messages"]), 2)

	def test_message_owners_are_opaque_for_guests(self):
		self._enter()
		area = self.g.guest_area().name
		self._put(self.B, 11, 11)
		frappe.set_user(self.B)
		self.g.send_guest_chat(area, "Welcome")
		frappe.set_user("Guest")
		owners = {m["owner"] for m in self.g.guest_space()["room"]["messages"]}
		self.assertEqual(owners, {self.g.public_id(self.B)})

	def test_idle_visits_end_and_only_live_ones_count(self):
		self._enter("Ada Guest")
		guest_id = frappe.local.ophice_guest_token.split(".")[0]
		entry = frappe.cache.hget(self.g.GUEST_CACHE_KEY, guest_id)
		entry["seen"] = ophice.time.time() - self.g.IDLE_SECONDS - 5
		frappe.cache.hset(self.g.GUEST_CACHE_KEY, guest_id, entry)
		self.assertEqual(self.g._current_guest(), (None, None))
		self.assertNotIn(guest_id, self.g._sessions())
		self.assertIsNone(frappe.cache.hget(ophice.PRESENCE_CACHE_KEY, self.g.GUEST_PREFIX + guest_id))
		self.assertNotIn("ip", entry)

	def test_employees_can_send_a_guest_out(self):
		me = self._enter()["me"]
		frappe.set_user(self.A)
		self.assertTrue(self.g.send_guest_out(me["user"]))
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			self.g.guest_space()
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			self.g.send_guest_out(me["user"])

	def test_purge_drops_invites_of_ended_visits(self):
		frappe.cache.hset(self.g.INVITE_CACHE_KEY, "gone00000000000000000", {"status": "pending", "by": self.A})
		self.g.purge_guests()
		self.assertIsNone(frappe.cache.hget(self.g.INVITE_CACHE_KEY, "gone00000000000000000"))

	def test_guests_are_not_people_in_a_meeting(self):
		frappe.set_user(self.A)
		room = ophice.save_area("Talk", "https://jitsi.example.org/Talk", 30, 20, 3, 3)
		frappe.cache.hset(
			ophice.PRESENCE_CACHE_KEY,
			"guest:abc",
			{"user": "guest:abc", "x": 31, "y": 21, "guest": True, "ts": ophice.time.time()},
		)
		self.assertNotIn("guest:abc", ophice._people_in(ophice._area(room)))
		frappe.cache.hdel(ophice.PRESENCE_CACHE_KEY, "guest:abc")

	def test_leaving_the_meeting_room_ends_the_invite(self):
		frappe.set_user(self.A)
		room = ophice.save_area("Room 1", "https://jitsi.example.org/Room1", 20, 10, 3, 3, kind="Customer meeting")
		frappe.set_user("Guest")
		me = self._enter()["me"]
		frappe.set_user(self.A)
		invite = self.g.invite_guest(me["user"], room)
		frappe.set_user("Guest")
		self.g.answer_invite(1)
		# Straight to the pin (the corridor allows it), arrived.
		self.g.guest_move(invite["pin"]["x"], invite["pin"]["y"])
		self.assertEqual(self.g.guest_space()["invite"]["status"], "arrived")
		# Back into the guest area: the invite is over, the room is closed again.
		self.g.guest_move(11, 11)
		space = self.g.guest_space()
		self.assertIsNone(space["invite"])
		self.assertEqual([a["name"] for a in space["areas"]], [self.g.guest_area().name])


class OphiceServerReviewTestCase(_OphiceRoomBase):
	"""Fixes from the review of the develop release: saves racing the countdown, kept chats, the
	scheduler, threads."""

	def test_a_save_that_raced_the_countdown_is_saved_not_burned(self):
		doc = frappe._dict(saved_by_a=1, saved_by_b=1, user_a=self.A, user_b=self.B)
		with patch.object(ophice, "_save") as save, patch.object(ophice, "_burn") as burn:
			self.assertEqual(ophice._burn_or_save(doc), "saved")
			save.assert_called_once()
			burn.assert_not_called()
		doc.saved_by_b = 0
		with patch.object(ophice, "_save") as save, patch.object(ophice, "_burn") as burn:
			self.assertEqual(ophice._burn_or_save(doc), "burned")
			burn.assert_called_once()

	def test_one_burn_vote_and_silence_keep_an_old_chat(self):
		frappe.set_user(self.A)
		area = self._area("Saved")
		self._put(self.B, 2, 2)
		ophice.send_area_message(area, "minutes of the meeting")
		name = ophice._running_batch_name(area)
		frappe.db.set_value(ophice.BATCH_DOCTYPE, name, "status", "Kept")
		ophice.vote_batch(name, "Burn")
		frappe.db.set_value(
			ophice.BATCH_DOCTYPE, name, "vote_until", ophice.add_to_date(ophice.now_datetime(), minutes=-1)
		)
		ophice._settle_batches()
		self.assertTrue(frappe.db.exists(ophice.BATCH_DOCTYPE, name))
		self.assertFalse(frappe.db.get_value(ophice.BATCH_DOCTYPE, name, "vote_until"))

	def test_one_failing_row_does_not_stop_the_scheduler(self):
		done = []

		def step(row):
			if row == 2:
				raise frappe.DoesNotExistError("gone meanwhile")
			done.append(row)

		with patch.object(ophice.frappe, "log_error") as logged:
			ophice._each([1, 2, 3], step, "test")
		self.assertEqual(done, [1, 3])
		logged.assert_called_once()

	def test_burning_deletes_threads_too(self):
		frappe.set_user(self.A)
		area = self._area("Saved")
		self._put(self.B, 2, 2)
		message = ophice.send_area_message(area, "start a thread on me")
		batch = frappe.get_doc(ophice.BATCH_DOCTYPE, ophice._running_batch_name(area))
		with patch.object(ophice.frappe, "get_all", wraps=frappe.get_all) as get_all:
			ophice._delete_channel(batch.raven_channel)
		asked = [c for c in get_all.call_args_list if c.args and c.args[0] == "Raven Channel"]
		self.assertTrue(asked and asked[0].kwargs["filters"]["is_thread"] == 1)
		self.assertIn(message["name"], asked[0].kwargs["filters"]["name"][1])
		self.assertFalse(frappe.db.exists("Raven Message", message["name"]))
		self.assertFalse(frappe.db.exists("Raven Channel", batch.raven_channel))

	def test_reading_endpoints_that_write_are_post_only(self):
		for fn in (ophice.get_area_chat,):
			self.assertIn("POST", frappe.allowed_http_methods_for_whitelisted_func[fn])
			self.assertNotIn("GET", frappe.allowed_http_methods_for_whitelisted_func[fn])


class OphiceAreaJitsiTestCase(FrappeTestCase):
	"""A space's Jitsi server is checked on every save, also in Desk (review of the release): the
	page loads external_api.js from it into the site's origin."""

	def setUp(self):
		frappe.set_user("Administrator")
		self.conf = patch.dict(frappe.conf, {"ophice_jitsi_domain": None, "ophice_jitsi_domains": ["jitsi.example.org"]})
		self.conf.start()

	def tearDown(self):
		self.conf.stop()
		frappe.db.rollback()

	def test_untrusted_server_refused_in_desk(self):
		frappe.db.delete(ophice.AREA_DOCTYPE)
		doc = frappe.get_doc(
			{
				"doctype": ophice.AREA_DOCTYPE,
				"title": "Desk edit",
				"meeting_url": "https://evil.example.com/Room",
				"jitsi_domain": "evil.example.com",
				"jitsi_room": "Room",
				"x": 1,
				"y": 1,
				"width": 2,
				"height": 2,
			}
		)
		with self.assertRaises(frappe.ValidationError):
			doc.insert(ignore_permissions=True)
		doc.jitsi_domain = "jitsi.example.org"
		doc.insert(ignore_permissions=True)


class OphicePhriendPlaceTestCase(_OphiceRoomBase):
	"""Phriend on the map (#2053): a map editor gives it one place; no meeting, no chat."""

	def setUp(self):
		super().setUp()
		frappe.db.delete(ophice.AREA_DOCTYPE)

	def test_one_place_without_meeting(self):
		frappe.set_user(self.A)  # map editor
		name = ophice.save_area("Phriend", "https://jitsi.example.org/Ignored", 5, 5, 1, 1, kind="Phriend")
		area = frappe.get_doc(ophice.AREA_DOCTYPE, name)
		self.assertEqual((area.kind, area.meeting_url, area.jitsi_room), ("Phriend", "", ""))
		with self.assertRaises(frappe.ValidationError):
			ophice.save_area("Second", "", 9, 9, 1, 1, kind="Phriend")
		# Not a meeting: nobody joins it, it has no chat, and the people list does not name it.
		self._put(self.B, 5, 5)
		frappe.set_user(self.B)
		with self.assertRaises(frappe.ValidationError):
			ophice.get_area_chat(name)
		b = next(p for p in ophice.get_people()["people"] if p["user"] == self.B)
		self.assertEqual(b["area"], "")
		frappe.set_user(self.B)  # not a map editor
		with self.assertRaises(frappe.PermissionError):
			ophice.save_area("Mine", "", 9, 9, 1, 1, kind="Phriend")


class OphiceInstantTestCase(FrappeTestCase):
	"""Times for "x minutes ago" carry their offset (AI review of !1301): the browser must not read
	the site's local time as its own."""

	def test_stored_times_become_instants(self):
		from datetime import datetime
		from zoneinfo import ZoneInfo

		with patch.object(ophice.frappe.utils, "get_system_timezone", return_value="Europe/Berlin"):
			value = ophice._as_instant("2026-11-22 10:00:00")
		self.assertEqual(datetime.fromisoformat(value), datetime(2026, 11, 22, 9, 0, tzinfo=ZoneInfo("UTC")))
		self.assertEqual(ophice._as_instant(None), "")
