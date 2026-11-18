# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""The plan-drafted label opens one merge request."""

import base64
import email.message
import importlib.util
import io
import os
import tempfile
import urllib.error
import urllib.parse
from pathlib import Path
from unittest.mock import MagicMock, patch

from frappe.tests.utils import FrappeTestCase

from phamos.gitlab_integration import issue_implement


def _ci_script():
    path = Path(__file__).resolve().parents[2] / ".gitlab" / "ai_issue_implement.py"
    spec = importlib.util.spec_from_file_location("ai_issue_implement", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _plan_script():
    path = Path(__file__).resolve().parents[2] / ".gitlab" / "ai_issue_plan.py"
    spec = importlib.util.spec_from_file_location("ai_issue_plan_for_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GITLAB = "https://git.example.test"
PROJECT = "https://git.example.test/phamos/phamos"
PLAN = (
    "## Requirements\n\n- Show the last editor.\n\n"
    "## Implementation plan\n\n- Add a form script and a test."
)
SOURCE = "phamos/public/js/timesheet_record.js"
TEST = "phamos/public/js/test_timesheet_record.js"


def _label(title):
    return {"title": title}


def _issue(**kwargs):
    data = {
        "iid": 7,
        "title": "Save button does nothing",
        "description": "Clicking save does nothing",
        "web_url": f"{PROJECT}/-/issues/7",
        "labels": ["plan-drafted"],
    }
    data.update(kwargs)
    return data


def _missing():
    return urllib.error.HTTPError(
        f"{GITLAB}/missing",
        404,
        "missing",
        email.message.EmailMessage(),
        io.BytesIO(b""),
    )


def _http(code):
    return urllib.error.HTTPError(
        f"{GITLAB}/denied",
        code,
        "denied",
        email.message.EmailMessage(),
        io.BytesIO(b""),
    )


def _change():
    return {
        "kind": "change",
        "title": "Show the last editor on the timesheet record",
        "description": "The form script reads modified_by.",
        "files": [
            {"path": SOURCE, "content": "frappe.ui.form.on('Timesheet Record', {});\n"},
            {"path": TEST, "content": "QUnit.test('shows the editor', function() {});\n"},
        ],
    }


class RecordingGitLab:
    def __init__(self, notes, files=None, mrs=None):
        self.notes = list(notes)
        self.files = dict(files or {})
        self.mrs = list(mrs or [])
        self.posts = []
        self.puts = []
        self.server = GITLAB
        self.commit_error = None

    def get(self, path, **params):
        if path.endswith("/notes"):
            return list(self.notes)
        if path == "/merge_requests":
            return list(self.mrs)
        if path.startswith("/repository/branches/"):
            raise _missing()
        if path.startswith("/repository/files/"):
            key = urllib.parse.unquote(path.split("/repository/files/", 1)[1])
            if key not in self.files:
                raise _missing()
            encoded = base64.b64encode(self.files[key].encode()).decode()
            return {"encoding": "base64", "content": encoded}
        return []

    def download(self, url):
        return None

    def post(self, path, payload):
        if path == "/repository/commits" and self.commit_error:
            raise self.commit_error
        self.posts.append((path, payload))
        if path == "/merge_requests":
            return {"iid": 15, "web_url": f"{PROJECT}/-/merge_requests/15", "title": payload["title"]}
        return {}

    def put(self, path, payload):
        self.puts.append(payload)


class TestIssueImplement(FrappeTestCase):
    def test_only_a_newly_added_plan_drafted_label_is_queued(self):
        payload = {
            "object_attributes": {"action": "update", "iid": 7},
            "project": {"path_with_namespace": "phamos/phamos", "default_branch": "develop"},
            "changes": {
                "labels": {
                    "previous": [_label("implementation plan")],
                    "current": [_label("plan-drafted")],
                }
            },
        }
        with (
            patch("frappe.db.get_single_value", return_value="phamos/phamos"),
            patch("frappe.enqueue") as enqueue,
        ):
            issue_implement.enqueue_issue_implement(payload, ["plan-drafted"], 42)
        enqueue.assert_called_once()
        self.assertEqual(enqueue.call_args.kwargs["issue_iid"], "7")

        with (
            patch("frappe.db.get_single_value", return_value="phamos/phamos"),
            patch("frappe.enqueue") as enqueue,
        ):
            issue_implement.enqueue_issue_implement(
                {
                    "object_attributes": {"action": "update", "iid": 7},
                    "project": {"path_with_namespace": "phamos/phamos", "default_branch": "develop"},
                    "changes": {
                        "labels": {
                            "previous": [_label("plan-drafted")],
                            "current": [_label("plan-drafted"), _label("mr-opened")],
                        }
                    },
                },
                ["plan-drafted", "mr-opened"],
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
            issue_implement.enqueue_issue_implement(payload, ["plan-drafted"], 99)
        enqueue.assert_not_called()

    def test_the_pipeline_is_started_with_the_plan_drafted_label(self):
        settings = MagicMock(gitlab_url=GITLAB + "/")
        response = MagicMock(status_code=201, text="")
        with (
            patch.object(issue_implement, "_access_token", return_value="glpat-test"),
            patch("frappe.get_single", return_value=settings),
            patch.object(issue_implement.requests, "post", return_value=response) as post,
        ):
            issue_implement.trigger_implement_pipeline("42", "7", "develop")
        post.assert_called_once_with(
            f"{GITLAB}/api/v4/projects/42/pipeline",
            headers={"PRIVATE-TOKEN": "glpat-test"},
            json={
                "ref": "develop",
                "variables": [
                    {"key": "AI_ISSUE_IID", "value": "7"},
                    {"key": "AI_ISSUE_LABEL", "value": "plan-drafted"},
                ],
            },
            timeout=30,
        )

    def test_a_change_opens_one_merge_request(self):
        script = _ci_script()
        plan = _plan_script().comment_body(3, "plan", "6", PLAN)
        gl = RecordingGitLab([{"id": 8, "body": plan, "system": False}])
        seen = {}

        def implement(*args):
            seen["plan"] = args[2]
            return _change()

        with (
            tempfile.TemporaryDirectory() as root,
            patch.object(script, "call_implement", side_effect=implement),
            patch.dict(os.environ, {"AI_ISSUE_REPO": root, "CI_COMMIT_REF_NAME": "develop"}),
        ):
            script.analysis()._SOURCE_CACHE = None
            posted = script.implement_issue(gl, _issue())

        self.assertTrue(posted)
        self.assertIn("Implementation plan", seen["plan"])
        commit = next(payload for path, payload in gl.posts if path == "/repository/commits")
        self.assertEqual(commit["branch"], "phamos/phamos#7_develop")
        self.assertEqual(commit["start_branch"], "develop")
        self.assertEqual(
            [item["file_path"] for item in commit["actions"]],
            [SOURCE, TEST],
        )
        self.assertTrue(all(item["action"] == "create" for item in commit["actions"]))
        mr = next(payload for path, payload in gl.posts if path == "/merge_requests")
        self.assertEqual(mr["source_branch"], "phamos/phamos#7_develop")
        self.assertEqual(mr["target_branch"], "develop")
        self.assertIn("Issue #7", mr["description"])
        self.assertIn("does not merge", mr["description"])
        note = next(payload["body"] for path, payload in gl.posts if path == "/issues/7/notes")
        self.assertIn("kind=mr", note)
        self.assertIn("mr=15", note)
        self.assertIn(f"{PROJECT}/-/merge_requests/15", note)
        self.assertEqual(gl.puts, [{
            "add_labels": "mr-opened",
            "remove_labels": "plan-drafted",
        }])

    def test_no_change_posts_the_finding_and_skips_the_merge_request(self):
        script = _ci_script()
        plan = _plan_script().comment_body(3, "plan", "6", PLAN)
        gl = RecordingGitLab([{"id": 8, "body": plan, "system": False}])

        def implement(*args):
            return {
                "kind": "no-change",
                "body": "The form sidebar already shows Modified and Modified By.",
            }

        with (
            tempfile.TemporaryDirectory() as root,
            patch.object(script, "call_implement", side_effect=implement),
            patch.dict(os.environ, {"AI_ISSUE_REPO": root}),
        ):
            script.analysis()._SOURCE_CACHE = None
            posted = script.implement_issue(gl, _issue())

        self.assertTrue(posted)
        self.assertFalse(any(path == "/repository/commits" for path, _payload in gl.posts))
        self.assertFalse(any(path == "/merge_requests" for path, _payload in gl.posts))
        note = next(payload["body"] for path, payload in gl.posts if path.endswith("/notes"))
        self.assertIn("kind=no-change", note)
        self.assertIn("Modified By", note)
        self.assertEqual(gl.puts, [{
            "add_labels": "no-change",
            "remove_labels": "plan-drafted",
        }])

    def test_an_existing_result_does_not_open_another_merge_request(self):
        script = _ci_script()
        note = script.comment_body("mr", "Opened !15: Show the editor", "15")
        gl = RecordingGitLab([{"id": 9, "body": note, "system": False}])

        with patch.object(script, "call_implement", side_effect=AssertionError("model ran again")):
            posted = script.implement_issue(gl, _issue())

        self.assertFalse(posted)
        self.assertEqual(gl.posts, [])
        self.assertEqual(gl.puts, [{
            "add_labels": "mr-opened",
            "remove_labels": "plan-drafted",
        }])

    def test_an_open_merge_request_is_reused(self):
        script = _ci_script()
        plan = _plan_script().comment_body(3, "plan", "6", PLAN)
        gl = RecordingGitLab(
            [{"id": 8, "body": plan, "system": False}],
            mrs=[{
                "iid": 15,
                "title": "Show the editor",
                "web_url": f"{PROJECT}/-/merge_requests/15",
            }],
        )

        with patch.object(script, "call_implement", side_effect=AssertionError("model ran again")):
            posted = script.implement_issue(gl, _issue())

        self.assertTrue(posted)
        self.assertFalse(any(path == "/repository/commits" for path, _payload in gl.posts))
        note = next(payload["body"] for path, payload in gl.posts if path.endswith("/notes"))
        self.assertIn("!15", note)
        self.assertEqual(gl.puts[0]["add_labels"], "mr-opened")

    def test_a_bad_reply_is_marked_failed(self):
        script = _ci_script()
        plan = _plan_script().comment_body(3, "plan", "6", PLAN)
        gl = RecordingGitLab([{"id": 8, "body": plan, "system": False}])

        with (
            tempfile.TemporaryDirectory() as root,
            patch.object(script, "call_implement", return_value={
                "kind": "failed",
                "body": "The reply was not a merge request with a test.",
            }),
            patch.dict(os.environ, {"AI_ISSUE_REPO": root}),
        ):
            script.analysis()._SOURCE_CACHE = None
            posted = script.implement_issue(gl, _issue())

        self.assertTrue(posted)
        note = next(payload["body"] for path, payload in gl.posts if path.endswith("/notes"))
        self.assertIn("kind=failed", note)
        self.assertEqual(gl.puts[0]["add_labels"], "implement-failed")
        self.assertFalse(any(path == "/merge_requests" for path, _payload in gl.posts))

    def test_a_refused_push_does_not_open_a_merge_request(self):
        script = _ci_script()
        plan = _plan_script().comment_body(3, "plan", "6", PLAN)
        gl = RecordingGitLab([{"id": 8, "body": plan, "system": False}])
        gl.commit_error = _http(403)

        with (
            tempfile.TemporaryDirectory() as root,
            patch.object(script, "call_implement", return_value=_change()),
            patch.dict(os.environ, {"AI_ISSUE_REPO": root, "CI_COMMIT_REF_NAME": "develop"}),
        ):
            script.analysis()._SOURCE_CACHE = None
            posted = script.implement_issue(gl, _issue())

        self.assertTrue(posted)
        note = next(payload["body"] for path, payload in gl.posts if path.endswith("/notes"))
        self.assertIn("kind=failed", note)
        self.assertIn("403", note)
        self.assertFalse(any(path == "/merge_requests" for path, _payload in gl.posts))
        self.assertEqual(gl.puts[0]["add_labels"], "implement-failed")

    def test_files_that_already_match_do_not_open_a_merge_request(self):
        script = _ci_script()
        plan = _plan_script().comment_body(3, "plan", "6", PLAN)
        change = _change()
        gl = RecordingGitLab(
            [{"id": 8, "body": plan, "system": False}],
            files={item["path"]: item["content"] for item in change["files"]},
        )

        with (
            tempfile.TemporaryDirectory() as root,
            patch.object(script, "call_implement", return_value=change),
            patch.dict(os.environ, {"AI_ISSUE_REPO": root}),
        ):
            script.analysis()._SOURCE_CACHE = None
            posted = script.implement_issue(gl, _issue())

        self.assertTrue(posted)
        self.assertFalse(any(path == "/repository/commits" for path, _payload in gl.posts))
        note = next(payload["body"] for path, payload in gl.posts if path.endswith("/notes"))
        self.assertIn("kind=no-change", note)
        self.assertEqual(gl.puts[0]["add_labels"], "no-change")

    def test_poll_skips_an_issue_that_already_has_a_result(self):
        script = _ci_script()
        done = _issue(iid=8)
        fresh = _issue(iid=9)
        marker = script.comment_body("mr", "Opened !4: Done", "4")
        plan = _plan_script().comment_body(3, "plan", "6", PLAN)
        posts = []

        class FakeGitLab(RecordingGitLab):
            def get(self, path, **params):
                if path == "/issues":
                    return [done, fresh]
                if path == "/issues/8/notes":
                    return [{"id": 1, "body": marker, "system": False}]
                if path == "/issues/9/notes":
                    return [{"id": 2, "body": plan, "system": False}]
                return super().get(path, **params)

            def post(self, path, payload):
                posts.append(path)
                return super().post(path, payload)

        gl = FakeGitLab([])
        with (
            tempfile.TemporaryDirectory() as root,
            patch.object(script, "call_implement", return_value=_change()),
            patch.dict(os.environ, {"AI_ISSUE_REPO": root, "AI_ISSUE_POLL_LIMIT": "1", "CI_COMMIT_REF_NAME": "develop"}),
        ):
            script.analysis()._SOURCE_CACHE = None
            script.poll(gl)
        self.assertEqual(posts, [
            "/repository/commits",
            "/merge_requests",
            "/issues/9/notes",
        ])

    def test_the_branch_is_the_issue_reference_plus_the_target(self):
        script = _ci_script()
        issue = _issue(iid=1952, references={"full": "phamos/phamos#1952"})
        with patch.dict(os.environ, {"CI_COMMIT_REF_NAME": "develop"}):
            self.assertEqual(script.branch_name(issue), "phamos/phamos#1952_develop")

    def test_parse_accepts_a_change_and_rejects_an_unsafe_path(self):
        script = _ci_script()
        parsed = script.parse_implementation(
            '```json\n{"kind":"change","title":"Show the editor","description":"Why",'
            '"files":[{"path":"phamos/test_editor.py","content":"def test_editor():\\n    pass\\n"}]}\n```'
        )
        self.assertEqual(parsed["kind"], "change")
        self.assertEqual(parsed["files"][0]["path"], "phamos/test_editor.py")
        self.assertIsNone(script.parse_implementation(
            '{"kind":"change","title":"Bad","files":[{"path":"../secrets.txt","content":"x"}]}'
        ))
        self.assertIsNone(script.parse_implementation(
            '{"kind":"change","title":"Bad","files":[{"path":".gitlab/ai_issue_implement.py","content":"x"}]}'
        ))
        self.assertIsNone(script.parse_implementation(
            '{"kind":"change","title":"No test","files":[{"path":"phamos/form.js","content":"var x = 1;\\n"}]}'
        ))
        finding = script.parse_implementation('{"kind":"no-change","body":"The sidebar shows it."}')
        self.assertEqual(finding["body"], "The sidebar shows it.")
        self.assertIsNone(script.safe_path("/etc/passwd"))
        self.assertIsNone(script.safe_path("frappe/hooks.py"))
