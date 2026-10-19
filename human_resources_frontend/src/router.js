import { createSpaRouter } from "@spa/router.js"
import ChecklistsHome from "@spa/views/ChecklistsHome.vue"
import ContractsInbox from "./contracts/ContractsInbox.vue"
import ContractsOverview from "./contracts/ContractsOverview.vue"
import spaConfig from "./config"

export default createSpaRouter({
	config: spaConfig,
	routes: [
		{
			path: "/checklists/home",
			name: "ChecklistsHome",
			component: ChecklistsHome,
		},
		{
			path: "/contracts",
			name: "Contracts",
			component: ContractsOverview,
		},
		{
			path: "/contracts/list",
			name: "ContractsList",
			component: ContractsInbox,
		},
		{
			path: "/contracts/list/:name",
			name: "ContractDetail",
			component: ContractsInbox,
			props: true,
		},
	],
})
