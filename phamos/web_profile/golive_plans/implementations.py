"""Go-live Implementations (phamos/phamos#1496, step 5e of #1492).

Old URLs: `/implementations` and `implementations/<case>`. An old case page only leads to a case that
names its customer (customer approval); anonymous cases are reached through the overview, so an old
URL never ties a customer to an anonymous case.
"""

from phamos.web_profile.golive import section_plan


def plan():
	return section_plan("implementations", ["implementations"])
