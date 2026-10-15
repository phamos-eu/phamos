import { createSpaRouter } from "@spa/router.js"
import ChecklistsHome from "@spa/views/ChecklistsHome.vue"
import TodosInbox from "./views/TodosInbox.vue"
import TodosHome from "./views/TodosHome.vue"
import spaConfig from "./config"

export default createSpaRouter({
	config: spaConfig,
	rootRedirect: "/todos",
	routes: [
		{ path: "/todos", name: "Todos", component: TodosHome },
		{ path: "/todos/list", name: "TodosList", component: TodosInbox },
		{ path: "/todos/list/:name", name: "TodoDetail", component: TodosInbox, props: true },
		{ path: "/checklists/home", name: "ChecklistsHome", component: ChecklistsHome },
	],
})
