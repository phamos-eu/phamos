import { createRouter, createWebHistory } from "vue-router"
import IssuesHome from "@spa/views/IssuesHome.vue"
import IssuesInbox from "@spa/views/IssuesInbox.vue"
import TasksHome from "@spa/views/TasksHome.vue"
import TasksInbox from "@spa/views/TasksInbox.vue"
import { session } from "@spa/session.js"

/** Issues + Tasks routes shared by every department cockpit. */
export const coreRoutes = [
	{
		path: "/issues",
		name: "Issues",
		component: IssuesHome,
	},
	{
		path: "/issues/list",
		name: "IssuesList",
		component: IssuesInbox,
	},
	{
		path: "/issues/list/:name",
		name: "IssueDetail",
		component: IssuesInbox,
		props: true,
	},
	{
		path: "/tasks",
		name: "Tasks",
		component: TasksHome,
	},
	{
		path: "/tasks/gantt",
		name: "TasksGantt",
		component: TasksInbox,
	},
	{
		path: "/tasks/gantt/:name",
		name: "TaskDetail",
		component: TasksInbox,
		props: true,
	},
]

/**
 * Build a cockpit router: root redirect, the shared Issues/Tasks routes,
 * any cockpit-specific routes, and the login guard.
 */
export function createSpaRouter({ config, routes = [], rootRedirect = "/issues/list" }) {
	const router = createRouter({
		history: createWebHistory(config.basePath),
		routes: [{ path: "/", redirect: rootRedirect }, ...coreRoutes, ...routes],
	})

	router.beforeEach((to, _from, next) => {
		if (!session.isLoggedIn) {
			const redirect = encodeURIComponent(
				`${config.basePath}${to.fullPath === "/" ? "" : to.fullPath}`
			)
			window.location.href = `/login?redirect-to=${redirect}`
			return
		}
		next()
	})

	return router
}
