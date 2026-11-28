import { createSpaRouter } from "@spa/router.js"
import ChecklistsHome from "@spa/views/ChecklistsHome.vue"
import TasksGanttPage from "./views/TasksGanttPage.vue"
import AppointmentsPage from "./views/AppointmentsPage.vue"
import IssueAssistantPage from "./views/IssueAssistantPage.vue"
import ContractsPage from "./views/ContractsPage.vue"
import spaConfig from "./config"

export default createSpaRouter({
	config: spaConfig,
	routes: [
		{
			path: "/checklists/home",
			name: "ChecklistsHome",
			component: ChecklistsHome,
		},
		// Same names as the shared routes, so they replace them (#1604): the Tasks Gantt gets
		// "Own department / All departments" (#1948).
		{
			path: "/tasks/gantt",
			name: "TasksGantt",
			component: TasksGanttPage,
		},
		{
			path: "/tasks/gantt/:name",
			name: "TaskDetail",
			component: TasksGanttPage,
		},
		// Company appointments (#1949)
		{
			path: "/appointments",
			name: "Appointments",
			component: AppointmentsPage,
		},
		// The Issue Assistant's learning, for trainers and System Managers (#2226)
		{
			path: "/issue-assistant",
			name: "IssueAssistant",
			component: IssueAssistantPage,
		},
		// Contracts: AVV, NDA, ... (#2148)
		{
			path: "/contracts",
			name: "Contracts",
			component: ContractsPage,
		},
	],
})
