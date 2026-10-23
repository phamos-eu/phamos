import { createRouter, createWebHistory } from "vue-router"
import { session } from "@spa/session.js"
import spaConfig from "./config"
import { allImplementations, defaultImplementation, loadScope, rememberImplementation } from "./scopeStore.js"
import Overview from "./views/Overview.vue"
import ComingSoon from "./views/ComingSoon.vue"
import Timesheets from "./views/Timesheets.vue"
import NoImplementation from "./views/NoImplementation.vue"

// Every page belongs to one implementation, so it is part of the URL: links into the cockpit
// (report emails, GitLab) always open the right one (#1672).
const sections = [
	{ path: "milestones", name: "Milestones", issue: "#1679" },
	{ path: "issues", name: "Issues", issue: "#1679, #1680" },
	{ path: "commercials", name: "Commercials", issue: "#1681" },
	{ path: "planning", name: "Planning", issue: "#1693, #1694" },
	{ path: "team", name: "Team", label: "Contact & Team", issue: "#1684" },
	{ path: "links", name: "Links", issue: "#1682" },
]

const router = createRouter({
	history: createWebHistory(spaConfig.basePath),
	routes: [
		{ path: "/", name: "Home", component: NoImplementation },
		{ path: "/:implementation", redirect: (to) => ({ name: "Overview", params: to.params }) },
		{ path: "/:implementation/overview", name: "Overview", component: Overview, props: true },
		{ path: "/:implementation/timesheets", name: "Timesheets", component: Timesheets, props: true },
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

export default router
