import { createSpaRouter } from "@spa/router.js"
import spaConfig from "./config"
import PmImplementationsHub from "./views/PmImplementationsHub.vue"
import PmWeeklyMonitoring from "./views/PmWeeklyMonitoring.vue"
import PmWeeklyMonitoringDetail from "./views/PmWeeklyMonitoringDetail.vue"

export default createSpaRouter({
	config: spaConfig,
	routes: [
		{
			path: "/implementations",
			name: "ImplementationsHub",
			component: PmImplementationsHub,
		},
		{
			path: "/implementations/weekly-monitoring",
			name: "WeeklyMonitoring",
			component: PmWeeklyMonitoring,
		},
		{
			path: "/implementations/weekly-monitoring/:name",
			name: "WeeklyMonitoringDetail",
			component: PmWeeklyMonitoringDetail,
			props: true,
		},
	],
})
