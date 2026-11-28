// Desk access to the open-month helper. Pages load it with frappe.require("open_months.bundle.js").
import { blankOpenMonths, isOpenMonth } from "./open_months";

frappe.provide("phamos.open_months");
Object.assign(phamos.open_months, { blankOpenMonths, isOpenMonth });
