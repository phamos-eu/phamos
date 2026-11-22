import { createRouter, createWebHistory } from "vue-router"

// Ophice lives at /ophice (#2070). The map is always there (App.vue); a cockpit opens over it at
// /ophice/open/<cockpit page>, e.g. /ophice/open/personal-cockpit/todos/plan (#2073).
const Empty = { render: () => null }

const router = createRouter({
	history: createWebHistory("/ophice"),
	routes: [
		{ path: "/", name: "Map", component: Empty },
		{ path: "/open/:path(.*)*", name: "Cockpit", component: Empty },
		{ path: "/:pathMatch(.*)*", redirect: { name: "Map" } },
	],
})

export default router
