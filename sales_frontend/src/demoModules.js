/**
 * Modules we might implement for a customer, shown as a pick-list while
 * planning a demo.
 *
 * Deliberately a plain JS constant for now: the selection isn't persisted
 * anywhere yet, so this is a drafting aid rather than data. Once demos need
 * to record what was actually shown, this should become a doctype (and the
 * selection a child table on Demo) instead of growing more structure here.
 */
export const DEMO_MODULES = [
	{ key: "crm", label: "CRM", description: "Leads, opportunities, follow-ups" },
	{ key: "sales", label: "Sales", description: "Quotations, orders, invoicing" },
	{ key: "purchasing", label: "Purchasing", description: "Suppliers, POs, receipts" },
	{ key: "stock", label: "Stock", description: "Warehouses, movements, valuation" },
	{ key: "manufacturing", label: "Manufacturing", description: "BOMs, work orders, capacity" },
	{ key: "projects", label: "Projects", description: "Tasks, timesheets, billing" },
	{ key: "accounting", label: "Accounting", description: "Ledger, payments, reconciliation" },
	{ key: "hr", label: "HR", description: "Employees, leave, expenses" },
	{ key: "support", label: "Support", description: "Issues, SLAs, customer portal" },
	{ key: "reporting", label: "Reporting", description: "Dashboards and KPIs" },
]
