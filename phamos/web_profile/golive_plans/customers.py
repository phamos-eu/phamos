"""Go-live Customers (phamos/phamos#1537, step 5g of #1492).

Old URLs: the reference pages (`/references`, `/referenzen`, `/customers`) and anything below them.
An old page only leads to a customer page that names the customer (approval); anonymous customers
are reached through the overview.
"""

from phamos.web_profile.golive import section_plan


def plan():
	return section_plan("customers", ["references", "referenzen", "customers"])
