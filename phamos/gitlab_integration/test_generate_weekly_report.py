from unittest import TestCase

from phamos.gitlab_integration.generate_weekly_report import (
    _format_issues_for_prompt,
    _group_deployed_issues_by_parent,
)


class TestGenerateWeeklyReport(TestCase):
    def test_groups_deployed_children_under_their_parent(self):
        parent = {
            "name": "project-291",
            "issue_id": "291",
            "title": "Correct PWA for Indo Dachdecker",
            "description": "Customer-facing feature",
            "issue_url": "https://gitlab.example.com/project/-/issues/291",
        }
        children = [
            {
                "name": "project-1088",
                "issue_id": "1088",
                "title": "Correct numbers in implementation",
                "description": "Use source values",
                "parent_issue": parent["name"],
                "merged_to_production_at": "2026-07-06 11:27:47",
            },
            {
                "name": "project-1089",
                "issue_id": "1089",
                "title": "Add regression coverage",
                "description": "Cover source values",
                "parent_issue": parent["name"],
                "testing_on_production_at": "2026-07-07 12:00:00",
            },
        ]

        report_issues = _group_deployed_issues_by_parent(children, [parent])

        self.assertEqual(len(report_issues), 1)
        self.assertEqual(report_issues[0]["issue_id"], "291")
        self.assertEqual(
            [source["issue_id"] for source in report_issues[0]["deployment_sources"]],
            ["1088", "1089"],
        )

    def test_keeps_standalone_issue_as_reportable_parent(self):
        standalone = {
            "name": "project-291",
            "issue_id": "291",
            "title": "Correct PWA for Indo Dachdecker",
            "description": "Customer-facing feature",
            "parent_issue": None,
            "merged_to_production_at": "2026-07-06 11:27:47",
        }

        report_issues = _group_deployed_issues_by_parent([standalone], [])

        self.assertEqual(len(report_issues), 1)
        self.assertEqual(report_issues[0]["issue_id"], "291")
        self.assertEqual(report_issues[0]["deployment_sources"][0]["issue_id"], "291")

    def test_prompt_marks_only_parent_as_reportable(self):
        report_issue = {
            "name": "project-291",
            "issue_id": "291",
            "title": "Parent feature",
            "description": "Customer outcome",
            "issue_url": "https://gitlab.example.com/project/-/issues/291",
            "comments": [],
            "deployment_sources": [
                {
                    "name": "project-1088",
                    "issue_id": "1088",
                    "title": "Child implementation",
                    "description": "Technical context",
                    "merged_to_production_at": "2026-07-06 11:27:47",
                    "comments": [],
                }
            ],
        }

        prompt = _format_issues_for_prompt([report_issue])

        self.assertIn("REPORTABLE PARENT ISSUE #291", prompt)
        self.assertIn("child issue; context only, never report separately", prompt)
        self.assertNotIn("REPORTABLE PARENT ISSUE #1088", prompt)
