"""Stakeholder Web Profiles get the explicit choice *Publish As* (phamos/phamos#1506).

Until now a profile was named exactly when *Approved to Be Named* was set; those records become
"Named", all others keep the default "Anonymous". Nothing changes on the website.
"""

import frappe


def execute():
	frappe.db.sql("update `tabStakeholder Web Profile` set publish_as = 'Named' where naming_approved = 1")
	frappe.db.sql("update `tabStakeholder Web Profile` set publish_as = 'Anonymous' where ifnull(publish_as, '') = ''")
