"""Go-live Modules (phamos/phamos#1495, step 5d of #1492). Old URLs: `/modules` and `modules/<module>`.

Old module pages without a Module Web Profile of the same name (e.g. `modules/healthcare`) lead to
the new overview; the go-live report lists them.
"""

from phamos.web_profile.golive import section_plan


def plan():
	return section_plan("modules", ["modules"])
