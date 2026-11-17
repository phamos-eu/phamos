# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""The implementation plan label starts a draft, one question at a time."""

import importlib.util
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from frappe.tests.utils import FrappeTestCase

from phamos.gitlab_integration import issue_plan


def _ci_script():
    path = Path(__file__).resolve().parents[2] / ".gitlab" / "ai_issue_plan.py"
    spec = importlib.util.spec_from_file_location("ai_issue_plan", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GITLAB = "https://git.example.test"
PROJECT = "https://git.example.test/phamos/phamos"


def _label(title):
    return {"title": title}


def _issue(**kwargs):
    data = {
        "iid": 7,
        "title": "Save button does nothing",
        "description": "Clicking save does nothing",
        "web_url": f"{PROJECT}/-/issues/7",
        "labels": ["implementation plan"],
    }
    data.update(kwargs)
    return data


class TestIssuePlan(FrappeTestCase):
    def test_only_a_newly_added_plan_label_is_queued(self):
        payload = {
            "object_attributes": {"action": "update", "iid": 7},
            "project": {"path_with_namespace": "phamos/phamos", "default_branch": "develop"},
            "changes": {
                "labels": {
                    "previous": [_label("Doing")],
                    "current": [_label("Doing"), _label("workflow::implementation plan")],
                }
            },
        }
        with (
            patch("frappe.db.get_single_value", return_value="phamos/phamos"),
            patch("frappe.enqueue") as enqueue,
        ):
            issue_plan.enqueue_issue_plan(payload, ["Doing", "workflow::implementation plan"], 42)
        enqueue.assert_called_once()
        self.assertEqual(
            enqueue.call_args.kwargs["issue_iid"],
            "7",
        )

        with (
            patch("frappe.db.get_single_value", return_value="phamos/phamos"),
            patch("frappe.enqueue") as enqueue,
        ):
            issue_plan.enqueue_issue_plan(
                {
                    "object_attributes": {"action": "update", "iid": 7},
                    "project": {"path_with_namespace": "phamos/phamos", "default_branch": "develop"},
                    "changes": {
                        "labels": {
                            "previous": [_label("implementation plan")],
                            "current": [_label("implementation plan"), _label("bug")],
                        }
                    },
                },
                ["implementation plan", "bug"],
                42,
            )
        enqueue.assert_not_called()

    def test_a_different_project_does_not_start_a_pipeline(self):
        payload = {
            "object_attributes": {"action": "open", "iid": 7},
            "project": {"path_with_namespace": "customer/app", "default_branch": "main"},
        }
        with (
            patch("frappe.db.get_single_value", return_value="phamos/phamos"),
            patch("frappe.enqueue") as enqueue,
        ):
            issue_plan.enqueue_issue_plan(payload, ["implementation plan"], 99)
        enqueue.assert_not_called()

    def test_the_pipeline_is_started_with_the_plan_label(self):
        settings = MagicMock(gitlab_url=GITLAB + "/")
        response = MagicMock(status_code=201, text="")
        with (
            patch.object(issue_plan, "_access_token", return_value="glpat-test"),
            patch("frappe.get_single", return_value=settings),
            patch.object(issue_plan.requests, "post", return_value=response) as post,
        ):
            issue_plan.trigger_plan_pipeline("42", "7", "develop")
        post.assert_called_once_with(
            f"{GITLAB}/api/v4/projects/42/pipeline",
            headers={"PRIVATE-TOKEN": "glpat-test"},
            json={
                "ref": "develop",
                "variables": [
                    {"key": "AI_ISSUE_IID", "value": "7"},
                    {"key": "AI_ISSUE_LABEL", "value": "implementation plan"},
                ],
            },
            timeout=30,
        )

    def test_a_reply_queues_the_next_step_and_a_bot_note_does_not(self):
        payload = {
            "object_attributes": {
                "noteable_type": "Issue",
                "system": False,
                "note": "Use the Sales Invoice.",
            },
            "issue": {"iid": 7, "labels": [_label("implementation plan")]},
            "project": {"id": 42, "path_with_namespace": "phamos/phamos", "default_branch": "develop"},
        }
        with (
            patch("frappe.db.get_single_value", return_value="phamos/phamos"),
            patch("frappe.enqueue") as enqueue,
        ):
            issue_plan.enqueue_plan_from_note(payload)
        enqueue.assert_called_once()

        payload["object_attributes"]["note"] = "<!-- phamos-ai-issue-plan turn=1 kind=question reply=0 -->"
        with (
            patch("frappe.db.get_single_value", return_value="phamos/phamos"),
            patch("frappe.enqueue") as enqueue,
        ):
            issue_plan.enqueue_plan_from_note(payload)
        enqueue.assert_not_called()

        payload["object_attributes"]["note"] = "A comment on a bug."
        payload["issue"]["labels"] = [_label("bug")]
        with (
            patch("frappe.db.get_single_value", return_value="phamos/phamos"),
            patch("frappe.enqueue") as enqueue,
        ):
            issue_plan.enqueue_plan_from_note(payload)
        enqueue.assert_not_called()

    def test_the_first_comment_asks_one_question_and_keeps_the_label(self):
        script = _ci_script()
        posts = []
        label_updates = []

        class FakeGitLab:
            server = GITLAB

            def get(self, path, **params):
                return []

            def download(self, url):
                return None

            def post(self, path, payload):
                posts.append(payload["body"])

            def put(self, path, payload):
                label_updates.append(payload)

        def planner(title, description, thread, images, code, previous_kind, questions):
            self.assertIsNone(previous_kind)
            return "plan", "Ship the whole feature."

        with (
            tempfile.TemporaryDirectory() as root,
            patch.object(script, "call_planner", side_effect=planner),
            patch.dict(os.environ, {"AI_ISSUE_REPO": root}),
        ):
            script.analysis()._SOURCE_CACHE = None
            posted = script.plan_issue(FakeGitLab(), _issue())

        self.assertTrue(posted)
        self.assertEqual(label_updates, [])
        self.assertIn("kind=question", posts[0])
        self.assertIn("reply=0", posts[0])
        self.assertIn("Ship the whole feature.", posts[0])
        self.assertNotIn("kind=plan", posts[0])

    def test_a_run_with_no_reply_does_not_ask_again(self):
        script = _ci_script()
        question = script.comment_body(1, "question", "0", "Which doctype? I recommend Sales Invoice.")
        calls = []

        class FakeGitLab:
            server = GITLAB

            def get(self, path, **params):
                return [{"id": 3, "body": question, "system": False}]

            def download(self, url):
                return None

            def post(self, path, payload):
                raise AssertionError("posted while waiting")

            def put(self, path, payload):
                raise AssertionError("labels changed while waiting")

        with patch.object(script, "call_planner", side_effect=lambda *args: calls.append(args)):
            posted = script.plan_issue(FakeGitLab(), _issue())
        self.assertFalse(posted)
        self.assertEqual(calls, [])

    def test_a_reply_gets_the_next_question(self):
        script = _ci_script()
        question = script.comment_body(1, "question", "0", "Which doctype? I recommend Sales Invoice.")
        notes = [
            {"id": 3, "body": question, "system": False},
            {"id": 4, "body": "Sales Invoice.", "system": False, "author": {"username": "sonali"}},
        ]
        posts = []

        class FakeGitLab:
            server = GITLAB

            def get(self, path, **params):
                return list(notes)

            def download(self, url):
                return None

            def post(self, path, payload):
                posts.append(payload["body"])

            def put(self, path, payload):
                raise AssertionError("labels changed before approval")

        def planner(title, description, thread, images, code, previous_kind, questions):
            self.assertEqual(previous_kind, "question")
            self.assertIn("Sales Invoice.", thread)
            return "question", "Should it run on submit? I recommend yes."

        with (
            tempfile.TemporaryDirectory() as root,
            patch.object(script, "call_planner", side_effect=planner),
            patch.dict(os.environ, {"AI_ISSUE_REPO": root}),
        ):
            script.analysis()._SOURCE_CACHE = None
            posted = script.plan_issue(FakeGitLab(), _issue())
        self.assertTrue(posted)
        self.assertIn("kind=question", posts[0])
        self.assertIn("reply=4", posts[0])
        self.assertIn("Should it run on submit?", posts[0])

    def test_approving_the_summary_posts_the_draft_and_swaps_the_label(self):
        script = _ci_script()
        summary = script.comment_body(
            2,
            "summary",
            "4",
            "## Requirements\n\n- R1: Save the form.\n\n## Implementation plan\n\n- Update the save handler.",
        )
        notes = [
            {"id": 5, "body": summary, "system": False},
            {"id": 6, "body": "approved", "system": False},
        ]
        posts = []
        label_updates = []

        class FakeGitLab:
            server = GITLAB

            def get(self, path, **params):
                return list(notes)

            def download(self, url):
                return None

            def post(self, path, payload):
                posts.append(payload["body"])

            def put(self, path, payload):
                label_updates.append(payload)

        with patch.object(script, "call_planner", side_effect=AssertionError("planner ran after approval")):
            posted = script.plan_issue(FakeGitLab(), _issue())
        self.assertTrue(posted)
        self.assertIn("kind=plan", posts[0])
        self.assertIn("reply=6", posts[0])
        self.assertIn("## Requirements", posts[0])
        self.assertIn("## Implementation plan", posts[0])
        self.assertIn("phamos-forge", posts[0])
        self.assertEqual(label_updates, [{
            "add_labels": "plan-drafted",
            "remove_labels": "implementation plan",
        }])

    def test_approved_before_a_summary_does_not_close_the_plan(self):
        script = _ci_script()
        question = script.comment_body(1, "question", "0", "Which doctype?")
        notes = [
            {"id": 3, "body": question, "system": False},
            {"id": 4, "body": "approved", "system": False},
        ]
        posts = []

        class FakeGitLab:
            server = GITLAB

            def get(self, path, **params):
                return list(notes)

            def download(self, url):
                return None

            def post(self, path, payload):
                posts.append(payload["body"])

            def put(self, path, payload):
                raise AssertionError("labels changed before a summary")

        def planner(*args):
            return "summary", "## Requirements\n\n- R1: Save.\n\n## Implementation plan\n\n- One change."

        with (
            tempfile.TemporaryDirectory() as root,
            patch.object(script, "call_planner", side_effect=planner),
            patch.dict(os.environ, {"AI_ISSUE_REPO": root}),
        ):
            script.analysis()._SOURCE_CACHE = None
            script.plan_issue(FakeGitLab(), _issue())
        self.assertIn("kind=summary", posts[0])
        self.assertNotIn("kind=plan", posts[0])

    def test_poll_skips_an_issue_that_is_waiting(self):
        script = _ci_script()
        question = script.comment_body(1, "question", "0", "Which doctype?")
        waiting = _issue(iid=8)
        fresh = _issue(iid=9)
        another = _issue(iid=10)
        posts = []
        seen = {}

        class FakeGitLab:
            server = GITLAB

            def get(self, path, **params):
                if path == "/issues":
                    seen["labels"] = params.get("labels")
                    return [waiting, fresh, another]
                iid = path.split("/")[2]
                if iid == "8":
                    return [{"id": 1, "body": question, "system": False}]
                return []

            def download(self, url):
                return None

            def post(self, path, payload):
                posts.append(path)

            def put(self, path, payload):
                return None

        with (
            tempfile.TemporaryDirectory() as root,
            patch.object(script, "call_planner", return_value=("question", "One question.")),
            patch.dict(os.environ, {"AI_ISSUE_REPO": root, "AI_ISSUE_POLL_LIMIT": "1"}),
        ):
            script.analysis()._SOURCE_CACHE = None
            script.poll(FakeGitLab())
        self.assertEqual(seen["labels"], "implementation plan")
        self.assertEqual(posts, ["/issues/9/notes"])

    def test_planning_sends_matching_repository_code(self):
        script = _ci_script()
        seen = {}

        def planner(title, description, thread, images, code, previous_kind, questions):
            seen["code"] = code
            return "question", "Created from the action panel?"

        class FakeGitLab:
            server = GITLAB

            def get(self, path, **params):
                return []

            def download(self, url):
                return None

            def post(self, path, payload):
                return None

            def put(self, path, payload):
                return None

        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "phamos"))
            with open(os.path.join(root, "phamos", "timesheet_record.py"), "w", encoding="utf-8") as handle:
                handle.write("def create_timesheet_record_from_action_panel():\n    return 'created'\n")
            script.analysis()._SOURCE_CACHE = None
            with (
                patch.object(script, "call_planner", side_effect=planner),
                patch.dict(os.environ, {"AI_ISSUE_REPO": root}),
            ):
                script.plan_issue(FakeGitLab(), _issue(
                    title="Timesheet record",
                    description="How is a timesheet record created from the action panel?",
                ))
        self.assertIn("phamos/timesheet_record.py", seen["code"])
        self.assertIn("create_timesheet_record_from_action_panel", seen["code"])

    def test_parse_and_approval(self):
        script = _ci_script()
        self.assertEqual(
            script.parse_turn('Sure\n{"kind":"summary","body":"## Requirements\\n\\n- R1"}'),
            ("summary", "## Requirements\n\n- R1"),
        )
        self.assertEqual(
            script.parse_turn("kind: summary\n\n## Requirements\n\n- R1"),
            ("summary", "## Requirements\n\n- R1"),
        )
        self.assertEqual(script.parse_turn("Which doctype? I recommend Sales Invoice."), (
            "question",
            "Which doctype? I recommend Sales Invoice.",
        ))
        self.assertIsNone(script.parse_turn("   "))
        self.assertTrue(script.accepts_summary("Approved."))
        self.assertFalse(script.accepts_summary("approved, but change the permission"))
        self.assertEqual(script.gate_kind("plan", None, 0), "question")
        self.assertEqual(script.gate_kind("question", "question", script.QUESTION_CAP), "summary")
