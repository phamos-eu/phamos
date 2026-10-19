"""Go-live Departments (phamos/phamos#1493, step 5b of #1492).

Old URLs: `/departments`, the Web Pages below it, and the two broken links used by the old person
pages (`management-department`, `it-development-department`).
"""

from phamos.web_profile.golive import section_plan

# Old slug → slug of the department's title, where the old pages used other names.
ALIASES = {
	"it": "software-development",
	"it-development-department": "software-development",
	"management-department": "management",
}


def plan():
	return section_plan("departments", ["departments"], aliases=ALIASES,
		extra_sources=["departments/management-department", "departments/it-development-department"])
