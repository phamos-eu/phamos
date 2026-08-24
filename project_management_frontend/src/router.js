import { createRouter, createWebHistory } from "vue-router"
import { session } from "./session"
import PmIssuesInbox from "./views/PmIssuesInbox.vue"
import PmTasksInbox from "./views/PmTasksInbox.vue"
import PmImplementationsHub from "./views/PmImplementationsHub.vue"
import PmWeeklyMonitoring from "./views/PmWeeklyMonitoring.vue"
import PmWeeklyMonitoringDetail from "./views/PmWeeklyMonitoringDetail.vue"

const routes = [
	{ path: "/", redirect: "/issues" },
	{
		path: "/issues",
		name: "Issues",
		component: PmIssuesInbox,
	},
	{
		path: "/issues/:name",
		name: "IssueDetail",
		component: PmIssuesInbox,
		props: true,
	},
	{
		path: "/tasks",
		name: "Tasks",
		component: PmTasksInbox,
	},
	{
		path: "/tasks/:name",
		name: "TaskDetail",
		component: PmTasksInbox,
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
	history: createWebHistory("/project-management-cockpit"),
	routes,
})

router.beforeEach((to, _from, next) => {
	if (!session.isLoggedIn) {
		window.location.href = `/login?redirect-to=/project-management-cockpit${to.fullPath === "/" ? "" : to.fullPath}`
		return
	}
	next()
})

export default router
