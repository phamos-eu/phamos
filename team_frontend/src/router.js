import { createSpaRouter } from "@spa/router.js"
import ChecklistsHome from "@spa/views/ChecklistsHome.vue"
import TeamAppointments from "./views/TeamAppointments.vue"
import TeamGitlab from "./views/TeamGitlab.vue"
import TeamIdeas from "./views/TeamIdeas.vue"
import TeamMates from "./views/TeamMates.vue"
import TeamSuccesses from "./views/TeamSuccesses.vue"
import TeamImplementations from "./views/TeamImplementations.vue"
import TeamStatistics from "./views/TeamStatistics.vue"
import spaConfig from "./config"

export default createSpaRouter({
	config: spaConfig,
	routes: [
		{
			path: "/checklists/home",
			name: "ChecklistsHome",
			component: ChecklistsHome,
		},
		{
			path: "/statistics",
			name: "TeamStatistics",
			component: TeamStatistics,
		},
		{
			path: "/implementations",
			name: "TeamImplementations",
			component: TeamImplementations,
		},
		{
			path: "/gitlab",
			name: "TeamGitlab",
			component: TeamGitlab,
		},
		{
			path: "/team-mates",
			name: "TeamMates",
			component: TeamMates,
		},
		{
			path: "/appointments",
			name: "TeamAppointments",
			component: TeamAppointments,
		},
		{
			path: "/ideas",
			name: "TeamIdeas",
			component: TeamIdeas,
		},
		{
			path: "/successes",
			name: "TeamSuccesses",
			component: TeamSuccesses,
		},
	],
})
