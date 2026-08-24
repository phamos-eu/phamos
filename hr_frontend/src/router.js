import { createRouter, createWebHistory } from "vue-router"
import { session } from "./session"
import HrIssuesInbox from "./views/HrIssuesInbox.vue"
import HrTasksInbox from "./views/HrTasksInbox.vue"

const routes = [
	{ path: "/", redirect: "/issues" },
	{
		path: "/issues",
		name: "Issues",
		component: HrIssuesInbox,
	},
	{
		path: "/issues/:name",
		name: "IssueDetail",
		component: HrIssuesInbox,
		props: true,
	},
	{
		path: "/tasks",
		name: "Tasks",
		component: HrTasksInbox,
	},
	{
		path: "/tasks/:name",
		name: "TaskDetail",
		component: HrTasksInbox,
		props: true,
	},
]

const router = createRouter({
	history: createWebHistory("/hr-cockpit"),
	routes,
})

router.beforeEach((to, _from, next) => {
	if (!session.isLoggedIn) {
		window.location.href = `/login?redirect-to=/hr-cockpit${to.fullPath === "/" ? "" : to.fullPath}`
		return
	}
	next()
})

export default router
