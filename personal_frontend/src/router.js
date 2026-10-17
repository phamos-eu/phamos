import { createSpaRouter } from "@spa/router.js"
import ChecklistsHome from "@spa/views/ChecklistsHome.vue"
import TodosInbox from "./views/TodosInbox.vue"
import TodosHome from "./views/TodosHome.vue"
import TodosMatrix from "./views/TodosMatrix.vue"
import CheckinsHome from "./views/CheckinsHome.vue"
import CheckinsList from "./views/CheckinsList.vue"
import MyContract from "./views/MyContract.vue"
import TodosPlan from "./views/TodosPlan.vue"
import spaConfig from "./config"
import TodosFocus from "./views/TodosFocus.vue"
import { ensureFocusLoaded } from "./focusStore.js"

const router = createSpaRouter({
	config: spaConfig,
	rootRedirect: "/todos/plan", // My Day answers "what do I do now" (#1602)
	routes: [
		{ path: "/todos", name: "Todos", component: TodosHome },
		{ path: "/todos/list", name: "TodosList", component: TodosInbox },
		{ path: "/todos/list/:name", name: "TodoDetail", component: TodosInbox, props: true },
		{ path: "/todos/matrix", name: "TodosMatrix", component: TodosMatrix },
		{ path: "/todos/focus", name: "TodosFocus", component: TodosFocus },
		{ path: "/todos/plan/:date?", name: "TodosPlan", component: TodosPlan },
		{ path: "/checklists/home", name: "ChecklistsHome", component: ChecklistsHome },
		{ path: "/checkins", name: "Checkins", component: CheckinsHome },
		{ path: "/checkins/list", name: "CheckinsList", component: CheckinsList },
		{ path: "/contract", name: "MyContract", component: MyContract },
	],
})

// While a focus session runs, the cockpit shows only the focus view (#1556). Leaving the
// session (always possible there) unlocks the rest again.
router.beforeEach(async (to) => {
	if (to.name === "TodosFocus") return true
	const session = await ensureFocusLoaded()
	return session ? { name: "TodosFocus" } : true
})

export default router
