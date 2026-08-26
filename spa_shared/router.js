import { createRouter, createWebHistory } from "vue-router"
import IssuesInbox from "@spa/views/IssuesInbox.vue"
import TasksInbox from "@spa/views/TasksInbox.vue"
import { session } from "@spa/session.js"

/** Issues + Tasks routes shared by every department cockpit. */
export const coreRoutes = [
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

/**
 * Build a cockpit router: root redirect, the shared Issues/Tasks routes,
 * any cockpit-specific routes, and the login guard.
 */
export function createSpaRouter({ config, routes = [], rootRedirect = "/issues" }) {
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
