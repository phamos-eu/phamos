"""Go-live Teams (phamos/phamos#1494, step 5c of #1492). Old URLs: `/teams` and `teams/<team>`."""

from phamos.web_profile.golive import section_plan


def plan():
	return section_plan("teams", ["teams"])
