import { createRouter, createWebHistory } from "vue-router"
import { call } from "frappe-ui"
import { session } from "@spa/session.js"
import spaConfig from "./config"
import { allImplementations, defaultImplementation, loadScope, rememberImplementation } from "./scopeStore.js"
import Overview from "./views/Overview.vue"
import ComingSoon from "./views/ComingSoon.vue"
import Timesheets from "./views/Timesheets.vue"
import SalesOrders from "./views/SalesOrders.vue"
import Issues from "./views/Issues.vue"
import IssueDetail from "./views/IssueDetail.vue"
import Links from "./views/Links.vue"
import Features from "./views/Features.vue"
import FeatureDetail from "./views/FeatureDetail.vue"
import NoImplementation from "./views/NoImplementation.vue"

// Every page belongs to one implementation, so it is part of the URL: links into the cockpit
// (report emails, GitLab) always open the right one (#1672).
const sections = [
	{ path: "milestones", name: "Milestones", issue: "#1679" },
	{ path: "planning", name: "Planning", issue: "#1693, #1694" },
	{ path: "team", name: "Team", label: "Contact & Team", issue: "#1684" },
]

const router = createRouter({
	history: createWebHistory(spaConfig.basePath),
	routes: [
		{ path: "/", name: "Home", component: NoImplementation },
		// From Phriend: find the implementation of the page or record, then show its issues there (#1671).
		{ path: "/status", name: "Status", component: NoImplementation, beforeEnter: resolveStatus },
		{ path: "/:implementation", redirect: (to) => ({ name: "Overview", params: to.params }) },
		{ path: "/:implementation/overview", name: "Overview", component: Overview, props: true },
		{ path: "/:implementation/timesheets", name: "Timesheets", component: Timesheets, props: true },
		// Reports made through Phriend (#1671). IssueDetail with `name` is what Phriend knows as an Issue page.
		{ path: "/:implementation/issues", name: "Issues", component: Issues, props: true },
		{ path: "/:implementation/issues/:name", name: "IssueDetail", component: IssueDetail, props: true },
		// Budget (was "Sales Orders"): the ordered budget and its Sales Orders; forecast follows (#1681).
		{ path: "/:implementation/budget", name: "Budget", component: SalesOrders, props: true },
		{ path: "/:implementation/sales-orders", redirect: (to) => ({ name: "Budget", params: to.params }) },
		{ path: "/:implementation/links", name: "Links", component: Links, props: true },
		// Features as list, Kanban and work breakdown (#1972)
		{ path: "/:implementation/features", name: "Features", component: Features, props: true },
		{ path: "/:implementation/features/:feature", name: "FeatureDetail", component: FeatureDetail, props: true },
		...sections.map((s) => ({
			path: `/:implementation/${s.path}`,
			name: s.name,
			component: ComingSoon,
			props: (route) => ({ implementation: route.params.implementation, section: s.label || s.name, issue: s.issue }),
		})),
	],
})

router.beforeEach(async (to) => {
	if (!session.isLoggedIn) {
		const redirect = encodeURIComponent(`${spaConfig.basePath}${to.fullPath === "/" ? "" : to.fullPath}`)
		window.location.href = `/login?redirect-to=${redirect}`
		return false
	}
	await loadScope()
	if (to.name === "Status") return true
	const wanted = to.params.implementation
	const known = allImplementations().some((i) => i.name === wanted)
	if (wanted && known) {
		rememberImplementation(wanted)
		return true
	}
	// No or unknown implementation in the URL: open the last used one, or show the empty state.
	const fallback = defaultImplementation()
	if (fallback) return { name: "Overview", params: { implementation: fallback }, replace: true }
	return to.name === "Home" ? true : { name: "Home", replace: true }
})

async function resolveStatus(to) {
	const query = {}
	for (const key of ["route", "ref_doctype", "ref_docname"]) if (to.query[key]) query[key] = to.query[key]
	const issue = to.query.issue || null
	let implementation = null
	try {
		implementation = await call(`${spaConfig.api}.resolve_status`, { ...query, issue })
	} catch (e) {
		implementation = null
	}
	// one report ("Follow its status"): straight to it, when it belongs to an implementation
	if (issue && implementation) return { name: "IssueDetail", params: { implementation, name: issue }, replace: true }
	implementation = implementation || defaultImplementation()
	if (!implementation) return { name: "Home", replace: true }
	return { name: "Issues", params: { implementation }, query, replace: true }
}

export default router
