import { createSpaRouter } from "@spa/router.js"
import spaConfig from "./config"
import LeadsFollowUps from "./views/LeadsFollowUps.vue"

const salesRoutes = [
	// The Leads nav group needs a route of its own; until the dashboard (#1758)
	// lands, it opens the follow-up list.
	{ path: "/leads", name: "Leads", redirect: { name: "LeadsFollowUps" } },
	{ path: "/leads/follow-ups", name: "LeadsFollowUps", component: LeadsFollowUps },
	{ path: "/leads/follow-ups/:name", name: "LeadDetail", component: LeadsFollowUps, props: true },
]

export default createSpaRouter({ config: spaConfig, routes: salesRoutes })
