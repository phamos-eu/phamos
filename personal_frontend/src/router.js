import { createSpaRouter } from "@spa/router.js"
import ChecklistsHome from "@spa/views/ChecklistsHome.vue"
import TodosInbox from "./views/TodosInbox.vue"
import spaConfig from "./config"

export default createSpaRouter({
	config: spaConfig,
	rootRedirect: "/todos",
	routes: [
		// The ToDo dashboard takes /todos in the next step (#1535); until then it is the list.
		{ path: "/todos", name: "Todos", redirect: "/todos/list" },
		{ path: "/todos/list", name: "TodosList", component: TodosInbox },
		{ path: "/todos/list/:name", name: "TodoDetail", component: TodosInbox, props: true },
		{ path: "/checklists/home", name: "ChecklistsHome", component: ChecklistsHome },
	],
})
