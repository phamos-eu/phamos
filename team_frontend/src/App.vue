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
import { computed, onBeforeUnmount, onMounted, ref } from "vue"
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
	// who is there and on what they work, live, with the team chat (#1978)
	{ name: "TeamMates", label: "Team mates", icon: "users", match: ["TeamMates"] },
	// appointments with leave and public holidays (#1979)
	{ name: "TeamAppointments", label: "Appointments", icon: "calendar", match: ["TeamAppointments"] },
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
	// Hours only, no currency (#1975)
	{ name: "TeamStatistics", label: "Statistics", icon: "bar-chart-2", match: ["TeamStatistics"] },
	{ name: "TeamImplementations", label: "Implementations", icon: "layers", match: ["TeamImplementations"] },
	// Team totals only (#1976)
	{ name: "TeamGitlab", label: "GitLab", icon: "git-branch", match: ["TeamGitlab"] },
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

async function loadTeams() {
	const data = await call(`${spaConfig.api}.get_teams`)
	// The active team is stored per user, not per window: when it was switched in another window,
	// this one would still show the old team's name while the server already works with the new
	// one. Start over on the new team instead.
	if (team.value && data.active && data.active !== team.value) {
		window.location.assign(spaConfig.basePath)
		return
	}
	team.value = data.active || ""
	teams.value = data.teams || []
}

function onVisible() {
	if (document.visibilityState === "visible") loadTeams()
}

onMounted(() => {
	loadTeams()
	document.addEventListener("visibilitychange", onVisible)
})

onBeforeUnmount(() => document.removeEventListener("visibilitychange", onVisible))

const pageTitle = computed(() => {
	if (route.name === "Tasks" || route.name === "TasksGantt" || route.name === "TaskDetail") {
		return "Tasks"
	}
	if (["ChecklistsHome", "Checklists", "ChecklistDetail"].includes(route.name)) return "Checklists"
	if (route.name === "TeamStatistics") return "Statistics"
	if (route.name === "TeamImplementations") return "Implementations"
	if (route.name === "TeamGitlab") return "GitLab"
	if (route.name === "TeamMates") return "Team mates"
	if (route.name === "TeamAppointments") return "Appointments"
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
	if (route.name === "TeamStatistics") return "Logged against available hours"
	if (route.name === "TeamImplementations") return "The team's implementations, in hours"
	if (route.name === "TeamGitlab") return "Closing times and SLA of the team"
	if (route.name === "TeamMates") return "Who is there, and on what they work"
	if (route.name === "TeamAppointments") return "The team's appointments, leave and public holidays"
	return "Team issues overview"
})
</script>
