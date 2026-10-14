"""Go-live Partners (phamos/phamos#1538, step 5h of #1492).

Old URLs: the partnership pages (`/partnerships`, `/partnerschaften`, `/partners`) and anything below
them. An old page only leads to a partner page that names the partner; anonymous partners are
reached through the overview.
"""

from phamos.web_profile.golive import section_plan


def plan():
	return section_plan("partners", ["partnerships", "partnerschaften", "partners"])
