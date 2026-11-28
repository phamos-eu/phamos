# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Bug and question labels start the CI job that uses the MR-review variables."""

import importlib.util
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from frappe.tests.utils import FrappeTestCase

from phamos.gitlab_integration import issue_analysis as analysis


def _ci_script():
    path = Path(__file__).resolve().parents[2] / ".gitlab" / "ai_issue_analysis.py"
    spec = importlib.util.spec_from_file_location("ai_issue_analysis", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

GITLAB = "https://git.example.test"
PROJECT = "https://git.example.test/phamos/phamos"
PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 16


def _label(title):
    return {"title": title}


class TestIssueAnalysis(FrappeTestCase):
    def test_only_a_newly_added_bug_or_question_is_queued(self):
        added = analysis.newly_added_analysis_labels(
            {
                "object_attributes": {"action": "update"},
                "changes": {
                    "labels": {
                        "previous": [_label("Doing")],
                        "current": [_label("Doing"), _label("type::Bug"), _label("Question")],
                    }
                },
            },
            ["Doing", "type::Bug", "Question"],
        )
        self.assertEqual(added, ["bug", "question"])

        self.assertEqual(
            analysis.newly_added_analysis_labels(
                {
                    "object_attributes": {"action": "update"},
                    "changes": {"title": {"previous": "Old", "current": "New"}},
                },
                ["bug"],
            ),
            [],
        )
        self.assertEqual(
            analysis.newly_added_analysis_labels(
                {
                    "object_attributes": {"action": "update"},
                    "changes": {"labels": {"previous": [_label("bug")], "current": []}},
                },
                [],
            ),
            [],
        )

    def test_an_issue_opened_with_the_label_counts(self):
        self.assertEqual(
            analysis.newly_added_analysis_labels(
                {"object_attributes": {"action": "open"}},
                ["question"],
            ),
            ["question"],
        )

    def test_image_urls_stay_on_the_gitlab_host(self):
        script = _ci_script()
        text = (
            "See ![screen](/uploads/abc/screen.png) and "
            '<img src="https://cdn.example.test/x.png"> '
            "and ![again](https://git.example.test/phamos/phamos/uploads/abc/other.jpg)"
        )
        self.assertEqual(
            script.image_urls(text, PROJECT, GITLAB),
            [
                f"{PROJECT}/uploads/abc/screen.png",
                f"{GITLAB}/phamos/phamos/uploads/abc/other.jpg",
            ],
        )

    def test_a_different_project_does_not_start_a_pipeline(self):
        payload = {
            "object_attributes": {"action": "open", "iid": 7},
            "project": {"path_with_namespace": "customer/app", "default_branch": "main"},
        }
        with (
            patch("frappe.db.get_single_value", return_value="phamos/phamos"),
            patch("frappe.enqueue") as enqueue,
        ):
            analysis.enqueue_issue_analysis(payload, ["bug"], 99)
        enqueue.assert_not_called()

    def test_a_new_bug_label_queues_one_pipeline_after_commit(self):
        payload = {
            "object_attributes": {"action": "open", "iid": 7},
            "project": {"path_with_namespace": "phamos/phamos", "default_branch": "develop"},
        }
        with (
            patch("frappe.db.get_single_value", return_value="phamos/phamos"),
            patch("frappe.enqueue") as enqueue,
        ):
            analysis.enqueue_issue_analysis(payload, ["bug", "bug"], 42)
        enqueue.assert_called_once_with(
            "phamos.gitlab_integration.issue_analysis.trigger_analysis_pipeline",
            queue="short",
            timeout=60,
            enqueue_after_commit=True,
            project_id="42",
            issue_iid="7",
            label="bug",
            ref="develop",
        )

    def test_the_pipeline_is_started_with_the_gitlab_settings_token(self):
        settings = MagicMock(gitlab_url=GITLAB + "/")
        response = MagicMock(status_code=201, text="")
        with (
            patch.object(analysis, "_access_token", return_value="glpat-test"),
            patch("frappe.get_single", return_value=settings),
            patch.object(analysis.requests, "post", return_value=response) as post,
        ):
            analysis.trigger_analysis_pipeline("42", "7", "question", "develop")
        post.assert_called_once_with(
            f"{GITLAB}/api/v4/projects/42/pipeline",
            headers={"PRIVATE-TOKEN": "glpat-test"},
            json={
                "ref": "develop",
                "variables": [
                    {"key": "AI_ISSUE_IID", "value": "7"},
                    {"key": "AI_ISSUE_LABEL", "value": "question"},
                ],
            },
            timeout=30,
        )

    def test_the_ci_job_comments_once_from_the_review_token(self):
        script = _ci_script()
        issue = {
            "title": "Save button does nothing",
            "description": "Clicking save shows ![dialog](/uploads/abc/dialog.png)",
            "web_url": f"{PROJECT}/-/issues/7",
        }
        notes = []
        posts = []
        label_updates = []
        seen_images = []

        class FakeGitLab:
            def __init__(self, server, project_id, token):
                self.server = server.rstrip("/")
                self.token = token

            def get(self, path, **params):
                if path.endswith("/notes"):
                    return list(notes)
                return issue

            def download(self, url):
                return "image/png", PNG

            def post(self, path, payload):
                posts.append(payload["body"])
                notes.append({"body": payload["body"], "system": False})

            def put(self, path, payload):
                label_updates.append(payload)

        def claude(label, title, description, note_lines, images, code=""):
            seen_images.extend(images)
            return "The save button closes nothing."

        with (
            patch.object(script, "GitLab", FakeGitLab),
            patch.object(script, "call_claude", side_effect=claude),
            patch.dict(os.environ, {
                "AI_ISSUE_LABEL": "bug",
                "AI_ISSUE_IID": "7",
                "CI_SERVER_URL": GITLAB,
                "CI_PROJECT_ID": "42",
                "GITLAB_API_TOKEN": "glpat-review",
                "ANTHROPIC_API_KEY": "sk-from-ci",
            }),
        ):
            script.main()
            script.main()

        self.assertEqual(len(posts), 1)
        self.assertIn("The save button closes nothing.", posts[0])
        self.assertIn("phamos-ai-issue-analysis label=bug", posts[0])
        self.assertNotIn("sk-from-ci", posts[0])
        self.assertNotIn("glpat-review", posts[0])
        self.assertEqual(seen_images, [("image/png", PNG)])
        self.assertEqual(label_updates, [
            {"add_labels": "analysed", "remove_labels": "bug"},
            {"add_labels": "analysed", "remove_labels": "bug"},
        ])

    def test_poll_skips_an_issue_that_already_has_the_same_analysis(self):
        script = _ci_script()
        fresh = {
            "iid": 7,
            "title": "Save button does nothing",
            "description": "Clicking save does nothing",
            "web_url": f"{PROJECT}/-/issues/7",
            "labels": ["bug"],
        }
        done_title, done_description = "Old question", "Already answered"
        done_digest = script._digest("question", done_title, done_description)
        done = {
            "iid": 8,
            "title": done_title,
            "description": done_description,
            "web_url": f"{PROJECT}/-/issues/8",
            "labels": ["question"],
        }
        posts = []

        class FakeGitLab:
            def __init__(self, server, project_id, token):
                self.server = server.rstrip("/")

            def get(self, path, **params):
                if path == "/issues":
                    return {"bug": [fresh], "question": [done]}.get(params.get("labels"), [])
                if path == "/issues/8/notes":
                    return [{"body": script.MARKER.format(label="question", digest=done_digest), "system": False}]
                if path.endswith("/notes"):
                    return []
                return fresh

            def download(self, url):
                return None

            def post(self, path, payload):
                posts.append(path)

            def put(self, path, payload):
                return None

        with (
            patch.object(script, "GitLab", FakeGitLab),
            patch.object(script, "call_claude", return_value="The save handler is missing."),
            patch.dict(os.environ, {
                "AI_ISSUE_POLL": "true",
                "AI_ISSUE_IID": "",
                "AI_ISSUE_POLL_LIMIT": "5",
                "CI_SERVER_URL": GITLAB,
                "CI_PROJECT_ID": "42",
                "GITLAB_API_TOKEN": "glpat-review",
                "ANTHROPIC_API_KEY": "sk-from-ci",
            }),
        ):
            script.main()

        self.assertEqual(posts, ["/issues/7/notes"])

    def test_poll_reads_the_named_project_and_code_from_this_checkout(self):
        script = _ci_script()
        seen = {}

        class FakeGitLab:
            def __init__(self, server, project_id, token):
                seen["project_id"] = project_id
                self.server = server.rstrip("/")

            def get(self, path, **params):
                if path == "/issues" and params.get("labels") == "bug":
                    return [{
                        "iid": 79,
                        "title": "Timesheet record",
                        "description": "How is a timesheet record created from the action panel?",
                        "web_url": f"{GITLAB}/phamos/developer/-/issues/79",
                        "labels": ["bug"],
                    }]
                if path.endswith("/notes"):
                    return []
                return []

            def download(self, url):
                return None

            def post(self, path, payload):
                seen["note"] = path

            def put(self, path, payload):
                seen["labels"] = payload

        def claude(label, title, description, note_lines, images, code=""):
            seen["code"] = code
            return "Created from the action panel."

        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "phamos"))
            with open(os.path.join(root, "phamos", "timesheet_record.py"), "w", encoding="utf-8") as handle:
                handle.write("def create_timesheet_record_from_action_panel():\n    return 'created'\n")
            script._SOURCE_CACHE = None
            with (
                patch.object(script, "GitLab", FakeGitLab),
                patch.object(script, "call_claude", side_effect=claude),
                patch.dict(os.environ, {
                    "AI_ISSUE_POLL": "true",
                    "AI_ISSUE_IID": "",
                    "AI_ISSUE_PROJECT": "phamos/developer",
                    "AI_ISSUE_REPO": root,
                    "CI_SERVER_URL": GITLAB,
                    "CI_PROJECT_ID": "42",
                    "GITLAB_API_TOKEN": "glpat-review",
                    "ANTHROPIC_API_KEY": "sk-from-ci",
                }),
            ):
                script.main()

        self.assertEqual(seen["project_id"], "phamos/developer")
        self.assertEqual(seen["note"], "/issues/79/notes")
        self.assertEqual(seen["labels"], {"add_labels": "analysed", "remove_labels": "bug"})
        self.assertIn("phamos/timesheet_record.py", seen["code"])
        self.assertIn("create_timesheet_record_from_action_panel", seen["code"])

    def test_analysis_sends_matching_repository_code(self):
        script = _ci_script()
        seen = {}

        def claude(label, title, description, note_lines, images, code=""):
            seen["code"] = code
            return "Created from the action panel."

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

        issue = {
            "iid": 9,
            "title": "Timesheet record",
            "description": "How is a timesheet record created from the action panel?",
            "web_url": f"{PROJECT}/-/issues/9",
        }
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "phamos"))
            with open(os.path.join(root, "phamos", "timesheet_record.py"), "w", encoding="utf-8") as handle:
                handle.write("def create_timesheet_record_from_action_panel():\n    return 'created'\n")
            script._SOURCE_CACHE = None
            with (
                patch.object(script, "call_claude", side_effect=claude),
                patch.dict(os.environ, {"AI_ISSUE_REPO": root}),
            ):
                script.analyse_issue(FakeGitLab(), issue, "question")

        self.assertIn("phamos/timesheet_record.py", seen["code"])
        self.assertIn("create_timesheet_record_from_action_panel", seen["code"])

    def test_standard_apps_keep_the_custom_app_major_version(self):
        script = _ci_script()

        def write(path, text):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(text)

        with tempfile.TemporaryDirectory() as root:
            custom = os.path.join(root, "custom")
            apps = os.path.join(root, "apps")
            write(os.path.join(custom, "phamos", "__init__.py"), "__version__ = '15.32.0'\n")
            write(os.path.join(custom, "phamos", "hooks.py"), 'required_apps = ["erpnext", "hrms"]\n')
            write(os.path.join(apps, "frappe", "frappe", "__init__.py"), "__version__ = '15.47.0'\n")
            write(
                os.path.join(apps, "frappe", "frappe", "timesheet.py"),
                "def last_changed_by(timesheet):\n    return timesheet.modified_by\n",
            )
            write(os.path.join(apps, "erpnext", "erpnext", "__init__.py"), "__version__ = '16.0.0'\n")
            write(
                os.path.join(apps, "erpnext", "erpnext", "timesheet.py"),
                "def last_changed_by_v16(timesheet):\n    return 'version 16'\n",
            )
            write(os.path.join(apps, "hrms", "hrms", "__init__.py"), "__version__ = '15.1.0'\n")
            script._SOURCE_CACHE = None
            with patch.dict(os.environ, {"AI_ISSUE_STD_APPS": apps, "AI_ISSUE_REPO": custom}):
                matched = [name for name, _version, _path in script.matching_standard_apps(custom)]
                code, kept = script.relevant_standard_code(
                    "Timesheet last changed",
                    "Who last changed the timesheet?",
                    "",
                    custom,
                )
        self.assertEqual(matched, ["frappe", "hrms"])
        self.assertIn("frappe/timesheet.py", code)
        self.assertIn("last_changed_by", code)
        self.assertNotIn("last_changed_by_v16", code)
        self.assertGreaterEqual(kept, 1)

    def test_the_analysis_prompt_uses_the_functional_consultant(self):
        script = _ci_script()
        text = script.system_prompt("bug")
        self.assertIn("# Senior Functional Consultant", text)
        self.assertIn("This is a bug report", text)
        self.assertNotIn("disable-model-invocation", text)
