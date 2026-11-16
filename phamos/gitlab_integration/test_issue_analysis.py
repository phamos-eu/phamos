# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Bug and question labels start the CI job that uses the MR-review variables."""

import importlib.util
import os
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

        def claude(label, title, description, note_lines, images):
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
