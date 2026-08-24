import { createRouter, createWebHistory } from "vue-router"
import { session } from "./session"
import AccountingIssuesInbox from "./views/AccountingIssuesInbox.vue"
import AccountingTasksInbox from "./views/AccountingTasksInbox.vue"
import ReceiptsInbox from "./views/ReceiptsInbox.vue"

const routes = [
	{ path: "/", redirect: "/receipts" },
	{
		path: "/issues",
		name: "Issues",
		component: AccountingIssuesInbox,
	},
	{
		path: "/issues/:name",
		name: "IssueDetail",
		component: AccountingIssuesInbox,
		props: true,
	},
	{
		path: "/tasks",
		name: "Tasks",
		component: AccountingTasksInbox,
	},
	{
		path: "/tasks/:name",
		name: "TaskDetail",
		component: AccountingTasksInbox,
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
	history: createWebHistory("/accounting-cockpit"),
	routes,
})

router.beforeEach(async (to, from, next) => {
	if (!session.isLoggedIn) {
		window.location.href = `/login?redirect-to=/accounting-cockpit${to.fullPath === "/" ? "" : to.fullPath}`
		return
	}
	next()
})

export default router
