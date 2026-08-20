import { createRouter, createWebHistory } from "vue-router"
import { session } from "./session"
import Inbox from "./views/Inbox.vue"

const routes = [
	{
		path: "/",
		name: "Inbox",
		component: Inbox,
	},
	{
		path: "/issue/:name",
		name: "IssueDetail",
		component: Inbox,
		props: true,
	},
]

const router = createRouter({
	history: createWebHistory("/i-own-my-work"),
	routes,
})

router.beforeEach((to, _from, next) => {
	if (!session.isLoggedIn) {
		window.location.href = `/login?redirect-to=/i-own-my-work${to.fullPath === "/" ? "" : to.fullPath}`
		return
	}
	next()
})

export default router
