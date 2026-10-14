import { createSpaRouter } from "@spa/router.js"
import ChecklistsHome from "@spa/views/ChecklistsHome.vue"
import spaConfig from "./config"

export default createSpaRouter({
	config: spaConfig,
	routes: [
		{
			path: "/checklists/home",
			name: "ChecklistsHome",
			component: ChecklistsHome,
		},
	],
})
