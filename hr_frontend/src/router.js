import { createRouter, createWebHistory } from "vue-router"
import { session } from "./session"
import IssuesInbox from "@spa/views/IssuesInbox.vue"
import TasksInbox from "@spa/views/TasksInbox.vue"
import spaConfig from "./config"

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
]

const router = createRouter({
	history: createWebHistory(spaConfig.basePath),
	routes,
})

router.beforeEach((to, _from, next) => {
	if (!session.isLoggedIn) {
		const redirect = encodeURIComponent(
			`${spaConfig.basePath}${to.fullPath === "/" ? "" : to.fullPath}`
		)
		window.location.href = `/login?redirect-to=${redirect}`
		return
	}
	next()
})

export default router
