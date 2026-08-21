import { createRouter, createWebHistory } from "@ionic/vue-router"
import { session } from "./session"

const routes = [
	{
		path: "/",
		redirect: "/home",
	},
	{
		path: "/home",
		name: "Home",
		component: () => import("@/views/Home.vue"),
	},
	{
		path: "/detail/:name",
		name: "ScanDetail",
		component: () => import("@/views/ScanDetail.vue"),
		props: true,
	},
	{
		path: "/contact/:name",
		name: "ContactDetail",
		component: () => import("@/views/ContactDetail.vue"),
		props: true,
	},
]

const router = createRouter({
	history: createWebHistory("/scan"),
	routes,
})

router.beforeEach((to, _from, next) => {
	if (!session.isLoggedIn) {
		const redirect = `/scan${to.fullPath === "/" ? "/home" : to.fullPath}`
		window.location.href = `/login?redirect-to=${encodeURIComponent(redirect)}`
		return
	}
	next()
})

export default router
