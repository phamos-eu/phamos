import { createRouter, createWebHistory } from "vue-router"
import { session } from "./session"
import SalesIssuesInbox from "./views/SalesIssuesInbox.vue"
import SalesTasksInbox from "./views/SalesTasksInbox.vue"

const routes = [
	{ path: "/", redirect: "/issues" },
	{
		path: "/issues",
		name: "Issues",
		component: SalesIssuesInbox,
	},
	{
		path: "/issues/:name",
		name: "IssueDetail",
		component: SalesIssuesInbox,
		props: true,
	},
	{
		path: "/tasks",
		name: "Tasks",
		component: SalesTasksInbox,
	},
	{
		path: "/tasks/:name",
		name: "TaskDetail",
		component: SalesTasksInbox,
		props: true,
	},
]

const router = createRouter({
	history: createWebHistory("/sales-cockpit"),
	routes,
})

router.beforeEach(async (to, from, next) => {
	if (!session.isLoggedIn) {
		window.location.href = `/login?redirect-to=/sales-cockpit${to.fullPath === "/" ? "" : to.fullPath}`
		return
	}
	next()
})

export default router
