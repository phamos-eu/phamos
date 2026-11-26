# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Skill conditions: one Python expression, evaluated like Notification conditions."""

import frappe
from frappe import _


def validate_expression(expression):
	try:
		compile(expression, "<condition>", "eval")
	except SyntaxError as e:
		frappe.throw(_("The condition is not a valid Python expression: {0}").format(e.msg))


def evaluate(expression, context):
	"""True when the expression is empty or truthy for the context."""
	if not (expression or "").strip():
		return True
	return bool(frappe.safe_eval(expression, None, context))
