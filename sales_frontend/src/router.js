import { createSpaRouter } from "@spa/router.js"
import spaConfig from "./config"
import LeadsHome from "./views/LeadsHome.vue"
import LeadsFollowUps from "./views/LeadsFollowUps.vue"
import DemosInbox from "./views/DemosInbox.vue"

const salesRoutes = [
	{ path: "/leads", name: "Leads", component: LeadsHome },
	{ path: "/leads/follow-ups", name: "LeadsFollowUps", component: LeadsFollowUps },
	{ path: "/leads/follow-ups/:name", name: "LeadDetail", component: LeadsFollowUps, props: true },
	{ path: "/demos", name: "Demos", component: DemosInbox },
	{ path: "/demos/list", name: "DemosList", component: DemosInbox },
]

export default createSpaRouter({ config: spaConfig, routes: salesRoutes })
