<template>
	<CockpitShell :title="pageTitle" :subtitle="pageSubtitle">
		<template #sidebar>
			<CockpitSidebar label="Sales" storage-key="sales-spa-sidebar-collapsed" :items="navItems" />
		</template>
	</CockpitShell>
</template>

<script setup>
import { computed } from "vue"
import { useRoute } from "vue-router"
import CockpitShell from "@spa/components/CockpitShell.vue"
import CockpitSidebar from "@spa/components/CockpitSidebar.vue"

const route = useRoute()

const navItems = [
	{ name: "Issues", label: "Issues", icon: "inbox", match: ["Issues", "IssueDetail"] },
	{ name: "Tasks", label: "Tasks", icon: "check-square", match: ["Tasks", "TaskDetail"] },
]

const pageTitle = computed(() => {
	if (route.name === "Tasks" || route.name === "TaskDetail") return "Tasks"
	return "Issues"
})

const pageSubtitle = computed(() => {
	if (route.name === "Tasks" || route.name === "TaskDetail") {
		return "Sales department tasks"
	}
	return "Sales department issues"
})
</script>
