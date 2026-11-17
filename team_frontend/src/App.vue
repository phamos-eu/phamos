<template>
	<CockpitShell :title="pageTitle" :subtitle="pageSubtitle">
		<template #sidebar>
			<!-- The sidebar is named after the team; its menu leads to the user's other teams. -->
			<CockpitSidebar
				:label="team || __('Team')"
				storage-key="team-cockpit-sidebar-collapsed"
				:items="navItems"
				:menu-groups="teamGroups"
			/>
		</template>
	</CockpitShell>
</template>

<script setup>
import { computed, onMounted, ref } from "vue"
import { useRoute } from "vue-router"
import { call, toast } from "frappe-ui"
import CockpitShell from "@spa/components/CockpitShell.vue"
import CockpitSidebar from "@spa/components/CockpitSidebar.vue"
import { __ } from "@spa/utils/i18n.js"
import spaConfig from "./config"

const route = useRoute()
const team = ref("")
const teams = ref([])

const navItems = [
	{
		name: "Issues",
		label: "Issues",
		icon: "inbox",
		match: ["Issues"],
		children: [
			{ name: "IssuesList", label: "List", icon: "list", match: ["IssuesList", "IssueDetail"] },
		],
	},
	{
		name: "Tasks",
		label: "Tasks",
		icon: "check-square",
		match: ["Tasks"],
		children: [
			{ name: "TasksGantt", label: "Gantt", icon: "bar-chart-2", match: ["TasksGantt", "TaskDetail"] },
		],
	},
	{
		name: "ChecklistsHome",
		label: "Checklists",
		icon: "list",
		match: ["ChecklistsHome"],
		children: [
			{
				name: "Checklists",
				label: "Checklists",
				icon: "list",
				match: ["Checklists", "ChecklistDetail"],
			},
		],
	},
]

const teamGroups = computed(() => [
	{
		group: __("Teams"),
		items: teams.value
			.filter((row) => row.name !== team.value)
			.map((row) => ({ label: row.name, onClick: () => switchTeam(row.name) })),
	},
])

async function switchTeam(name) {
	try {
		await call(`${spaConfig.api}.set_active_team`, { team: name })
	} catch (e) {
		toast({ title: __("Could not switch the team"), text: e.messages?.[0] || e.message, icon: "x" })
		return
	}
	// Every list belongs to the old team, and the open record may not be the new team's: start over.
	window.location.assign(spaConfig.basePath)
}

onMounted(async () => {
	const data = await call(`${spaConfig.api}.get_teams`)
	team.value = data.active || ""
	teams.value = data.teams || []
})

const pageTitle = computed(() => {
	if (route.name === "Tasks" || route.name === "TasksGantt" || route.name === "TaskDetail") {
		return "Tasks"
	}
	if (["ChecklistsHome", "Checklists", "ChecklistDetail"].includes(route.name)) return "Checklists"
	return "Issues"
})

const pageSubtitle = computed(() => {
	if (route.name === "TasksGantt" || route.name === "TaskDetail") {
		return "Team tasks"
	}
	if (route.name === "Tasks") {
		return "Team tasks overview"
	}
	if (route.name === "ChecklistsHome") {
		return "Team checklist activity and workload"
	}
	if (route.name === "Checklists" || route.name === "ChecklistDetail") {
		return "Checklists linked to the team's issues and tasks"
	}
	if (route.name === "IssuesList" || route.name === "IssueDetail") {
		return "Team issues"
	}
	return "Team issues overview"
})
</script>
