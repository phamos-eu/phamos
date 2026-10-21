"""Go-live Industries (phamos/phamos#1497, step 5f of #1492). Old URLs: `/industries`, `industries/<industry>`."""

from phamos.web_profile.golive import section_plan

# Old slug → slug of the industry's title, where the old pages used other names.
ALIASES = {"healthcare": "health-care", "retail": "retail-wholesale"}


def plan():
	return section_plan("industries", ["industries"], aliases=ALIASES)
