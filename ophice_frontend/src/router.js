import { createRouter, createWebHistory } from "vue-router"
import Ophice from "./views/Ophice.vue"

// Ophice lives at /ophice (#2070). One page for now; the cockpits open inside it later (#2073).
const router = createRouter({
	history: createWebHistory("/ophice"),
	routes: [
		{ path: "/", name: "Ophice", component: Ophice },
		{ path: "/:pathMatch(.*)*", redirect: { name: "Ophice" } },
	],
})

export default router
