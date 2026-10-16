"""Create the AI Accountant role before Accounting Receipt syncs its DocPerm for it."""

from phamos.setup.accounting_receipt import ensure_role


def execute():
	ensure_role()
