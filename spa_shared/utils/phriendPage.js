// What Phriend records about the cockpit page a report comes from (#1900). Pure, so it can be
// tested without a browser; spa_shared/phriend.js feeds it the live route.

// Detail routes and the DocType their `name` parameter belongs to. A route not listed here is
// a page, not a record: the report then refers to the route only.
export const RECORD_ROUTES = {
	IssueDetail: "Issue",
	TaskDetail: "Task",
	ChecklistDetail: "Checklist",
	TodoDetail: "ToDo",
	MyLeaveDetail: "Leave Application",
	IdeaDetail: "Idea",
	IdeaWrite: "Idea",
	IdeaVoteDetail: "Idea",
	LeadDetail: "Lead",
	ReceiptDetail: "Accounting Receipt",
	MisDetail: "Monthly Implementation Summary",
	ContractDetail: "Employment Contract",
	WeeklyMonitoringDetail: "Implementation",
}

/**
 * @param {object} route   vue-router's current route ({ name, path, params, query })
 * @param {object} page    { base: "/sales-cockpit", cockpit: "Sales", heading: "Leads" }
 * @param {function} translate  __() for the DocType name shown as "Reported on"
 * @returns {{ route, where, ref_doctype, ref_docname, context }}
 */
export function pageContext(route, page, translate = (text) => text) {
	const doctype = RECORD_ROUTES[route?.name] || null
	const docname = doctype ? String(route.params?.name || "") || null : null
	const base = String(page?.base || "").replace(/^\/+|\/+$/g, "")
	const path = route?.path && route.path !== "/" ? route.path : ""
	const where = docname
		? `${translate(doctype)} ${docname}`
		: [page?.cockpit, page?.heading].filter(Boolean).join(" · ")
	return {
		route: `${base}${path}`.slice(0, 140),
		where,
		ref_doctype: docname ? doctype : null,
		ref_docname: docname,
		context: {
			app: page?.cockpit || base,
			// the query's keys only: its values can be search terms or names (GDPR review of !1162)
			route: { name: route?.name || null, path: route?.path || "", params: { ...(route?.params || {}) }, query: Object.keys(route?.query || {}) },
		},
	}
}

// What the badge on the ball counts: reports about this record, else about this page.
export function badgeArgs(context) {
	return context.ref_doctype
		? { ref_doctype: context.ref_doctype, ref_docname: context.ref_docname }
		: { route: context.route }
}
