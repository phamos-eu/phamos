import { createSpaRouter } from "@spa/router.js"
import spaConfig from "./config"
import LeadsFollowUps from "./views/LeadsFollowUps.vue"
import LeadsOverview from "./views/LeadsOverview.vue"

const salesRoutes = [
	// The Leads nav group opens the overview (#1758).
	{ path: "/leads", name: "Leads", redirect: { name: "LeadsOverview" } },
	{ path: "/leads/overview", name: "LeadsOverview", component: LeadsOverview },
	{ path: "/leads/follow-ups", name: "LeadsFollowUps", component: LeadsFollowUps },
	{ path: "/leads/follow-ups/:name", name: "LeadDetail", component: LeadsFollowUps, props: true },
]

export default createSpaRouter({ config: spaConfig, routes: salesRoutes })
