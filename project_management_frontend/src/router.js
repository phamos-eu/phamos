import { createRouter, createWebHistory } from "vue-router"
import { session } from "./session"
import IssuesInbox from "@spa/views/IssuesInbox.vue"
import TasksInbox from "@spa/views/TasksInbox.vue"
import spaConfig from "./config"
import PmImplementationsHub from "./views/PmImplementationsHub.vue"
import PmWeeklyMonitoring from "./views/PmWeeklyMonitoring.vue"
import PmWeeklyMonitoringDetail from "./views/PmWeeklyMonitoringDetail.vue"

const routes = [
	{ path: "/", redirect: "/issues" },
	{
		path: "/issues",
		name: "Issues",
		component: IssuesInbox,
	},
	{
		path: "/issues/:name",
		name: "IssueDetail",
		component: IssuesInbox,
		props: true,
	},
	{
		path: "/tasks",
		name: "Tasks",
		component: TasksInbox,
	},
	{
		path: "/tasks/:name",
		name: "TaskDetail",
		component: TasksInbox,
		props: true,
	},
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
]

const router = createRouter({
	history: createWebHistory(spaConfig.basePath),
	routes,
})

router.beforeEach((to, _from, next) => {
	if (!session.isLoggedIn) {
		window.location.href = `/login?redirect-to=${encodeURIComponent(`${spaConfig.basePath}${to.fullPath === "/" ? "" : to.fullPath}`)}`
		return
	}
	next()
})

export default router
