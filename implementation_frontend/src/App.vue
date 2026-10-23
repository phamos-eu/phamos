<template>
	<CockpitShell :title="pageTitle">
		<template #sidebar>
			<CockpitSidebar :label="__('Implementation Cockpit')" storage-key="implementation-cockpit-sidebar-collapsed" :items="navItems">
				<template #header="{ collapsed, toggle }">
					<ScopePicker :collapsed="collapsed" @toggle="toggle" />
				</template>
				<template #footer="{ collapsed }">
					<SidebarContact :collapsed="collapsed" />
				</template>
			</CockpitSidebar>
		</template>
	</CockpitShell>
</template>

<script setup>
import { computed, watch } from "vue"
import { useRoute } from "vue-router"
import CockpitShell from "@spa/components/CockpitShell.vue"
import CockpitSidebar from "@spa/components/CockpitSidebar.vue"
import { __ } from "@spa/utils/i18n.js"
import ScopePicker from "./components/ScopePicker.vue"
import SidebarContact from "./components/SidebarContact.vue"
import { loadImplementation } from "./implementationStore.js"

const route = useRoute()

watch(
	() => route.params.implementation,
	(name) => loadImplementation(name),
	{ immediate: true }
)

// Without an implementation there is nothing to navigate to.
const navItems = computed(() =>
	route.params.implementation
		? [
				{ name: "Overview", label: __("Overview"), icon: "grid" },
				{ name: "Milestones", label: __("Milestones"), icon: "flag" },
				{ name: "Issues", label: __("Issues"), icon: "inbox" },
				{ name: "Timesheets", label: __("Timesheets"), icon: "clock" },
				{ name: "SalesOrders", label: __("Sales Orders"), icon: "file-text" },
				{ name: "Planning", label: __("Planning"), icon: "calendar" },
				{ name: "Team", label: __("Contact & Team"), icon: "users" },
				{ name: "Links", label: __("Links"), icon: "link" },
			]
		: []
)

const pageTitle = computed(() => {
	const implementation = route.params.implementation
	const section = navItems.value.find((item) => item.name === route.name)
	if (!implementation) return __("Implementation Cockpit")
	return section && route.name !== "Overview" ? `${section.label} · ${implementation}` : implementation
})
</script>
