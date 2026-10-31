import { createSpaRouter } from "@spa/router.js"
import ChecklistsHome from "@spa/views/ChecklistsHome.vue"
import TodosInbox from "./views/TodosInbox.vue"
import TodosHome from "./views/TodosHome.vue"
import TodosMatrix from "./views/TodosMatrix.vue"
import CheckinsHome from "./views/CheckinsHome.vue"
import CheckinsList from "./views/CheckinsList.vue"
import MyLeave from "./views/MyLeave.vue"
import IssuesHome from "./views/IssuesHome.vue"
import TasksHome from "./views/TasksHome.vue"
import TodosPlan from "./views/TodosPlan.vue"
import spaConfig from "./config"
import TodosFocus from "./views/TodosFocus.vue"
import { ensureFocusLoaded } from "./focusStore.js"
import { CHECKINS, MY_DAY } from "./features.js"

// The cockpit opens on the last page used (decision of 2026-10-31); the first time on My Leave.
const LAST_PAGE_KEY = "personal-cockpit-last-page"
const FIRST_PAGE = "/leave"

function lastPage() {
	try {
		return localStorage.getItem(LAST_PAGE_KEY) || FIRST_PAGE
	} catch {
		return FIRST_PAGE
	}
}

const router = createSpaRouter({
	config: spaConfig,
	rootRedirect: () => lastPage(),
	routes: [
		{ path: "/todos", name: "Todos", component: TodosHome },
		{ path: "/todos/list", name: "TodosList", component: TodosInbox },
		{ path: "/todos/list/:name", name: "TodoDetail", component: TodosInbox, props: true },
		{ path: "/todos/matrix", name: "TodosMatrix", component: TodosMatrix },
		{ path: "/todos/focus", name: "TodosFocus", component: TodosFocus },
		...(MY_DAY ? [{ path: "/todos/plan/:date?", name: "TodosPlan", component: TodosPlan }] : []),
		{ path: "/checklists/home", name: "ChecklistsHome", component: ChecklistsHome },
		...(CHECKINS
			? [
					{ path: "/checkins", name: "Checkins", component: CheckinsHome },
					{ path: "/checkins/list", name: "CheckinsList", component: CheckinsList },
				]
			: []),
		// My Leave (#1714)
		{ path: "/leave", name: "MyLeave", component: MyLeave },
		{ path: "/leave/:name", name: "MyLeaveDetail", component: MyLeave, props: true },
		// Own start pages for Issues and Tasks (#1604); they replace the shared empty ones.
		{ path: "/issues", name: "Issues", component: IssuesHome },
		{ path: "/tasks", name: "Tasks", component: TasksHome },
	],
})

// While a focus session runs, the cockpit shows only the focus view (#1556). Leaving the
// session (always possible there) unlocks the rest again.
router.beforeEach(async (to) => {
	if (to.name === "TodosFocus") return true
	const session = await ensureFocusLoaded()
	return session ? { name: "TodosFocus" } : true
})

// Remember pages, not records: a detail URL may point at something deleted by the next visit.
router.afterEach((to) => {
	if (!to.name || to.name === "TodosFocus" || Object.keys(to.params).length) return
	try {
		localStorage.setItem(LAST_PAGE_KEY, to.path)
	} catch {
		/* private window: the cockpit opens on My Leave */
	}
})

export default router
