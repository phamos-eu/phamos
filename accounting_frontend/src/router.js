import { createRouter, createWebHistory } from "vue-router"
import { session } from "./session"
import IssuesInbox from "@spa/views/IssuesInbox.vue"
import TasksInbox from "@spa/views/TasksInbox.vue"
import spaConfig from "./config"
import ReceiptsInbox from "./views/ReceiptsInbox.vue"

const routes = [
	{ path: "/", redirect: "/receipts" },
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
		path: "/receipts",
		name: "Receipts",
		component: ReceiptsInbox,
	},
	{
		path: "/receipts/:name",
		name: "ReceiptDetail",
		component: ReceiptsInbox,
		props: true,
	},
]

const router = createRouter({
	history: createWebHistory(spaConfig.basePath),
	routes,
})

router.beforeEach(async (to, from, next) => {
	if (!session.isLoggedIn) {
		window.location.href = `/login?redirect-to=${encodeURIComponent(`${spaConfig.basePath}${to.fullPath === "/" ? "" : to.fullPath}`)}`
		return
	}
	next()
})

export default router
