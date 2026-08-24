<template>
	<aside
		class="flex h-full flex-none flex-col border-r border-gray-200 bg-white transition-[width] dark:border-gray-800 dark:bg-gray-900"
		:class="collapsed ? 'w-14' : 'w-52'"
	>
		<div
			class="flex h-12 flex-shrink-0 items-center border-b border-gray-200 px-3 dark:border-gray-800"
			:class="collapsed ? 'justify-center' : 'justify-between'"
		>
			<span v-if="!collapsed" class="truncate text-sm font-semibold text-gray-900 dark:text-gray-100">PM</span>
			<button
				type="button"
				class="rounded p-1.5 text-gray-500 hover:bg-gray-100 hover:text-gray-800 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-200"
				:title="collapsed ? 'Expand' : 'Collapse'"
				@click="toggle"
			>
				<FeatherIcon :name="collapsed ? 'chevrons-right' : 'chevrons-left'" class="h-4 w-4" />
			</button>
		</div>

		<nav class="flex flex-1 flex-col gap-1 overflow-y-auto p-2">
			<router-link
				v-for="item in topItems"
				:key="item.name"
				:to="{ name: item.name }"
				class="flex items-center gap-2 rounded-md px-2 py-2 text-sm font-medium transition"
				:class="navClass(item)"
				:title="collapsed ? item.label : undefined"
			>
				<FeatherIcon :name="item.icon" class="h-4 w-4 flex-shrink-0" />
				<span v-if="!collapsed" class="truncate">{{ item.label }}</span>
			</router-link>

			<div class="mt-1">
				<button
					type="button"
					class="flex w-full items-center gap-2 rounded-md px-2 py-2 text-sm font-medium transition"
					:class="implementationsGroupActive ? activeClass : inactiveClass"
					:title="collapsed ? 'Implementations' : undefined"
					@click="toggleImplementations"
				>
					<FeatherIcon name="layers" class="h-4 w-4 flex-shrink-0" />
					<span v-if="!collapsed" class="flex-1 truncate text-left">Implementations</span>
					<FeatherIcon
						v-if="!collapsed"
						:name="implementationsOpen ? 'chevron-down' : 'chevron-right'"
						class="h-3.5 w-3.5 flex-shrink-0 opacity-70"
					/>
				</button>

				<div v-if="implementationsOpen && !collapsed" class="ml-2 mt-1 flex flex-col gap-1 border-l border-gray-200 pl-2 dark:border-gray-700">
					<router-link
						v-for="item in implementationItems"
						:key="item.name"
						:to="{ name: item.name }"
						class="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm transition"
						:class="navClass(item, true)"
					>
						<FeatherIcon :name="item.icon" class="h-3.5 w-3.5 flex-shrink-0" />
						<span class="truncate">{{ item.label }}</span>
					</router-link>
				</div>
			</div>
		</nav>
	</aside>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue"
import { useRoute } from "vue-router"

const STORAGE_KEY = "pm-spa-sidebar-collapsed"
const IMPL_NAV_KEY = "pm-spa-impl-nav-open"

const route = useRoute()
const collapsed = ref(false)
const implementationsOpen = ref(true)

const activeClass =
	"bg-gray-900 text-white dark:bg-gray-100 dark:text-gray-900"
const inactiveClass =
	"text-gray-600 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-100"

const topItems = [
	{ name: "Issues", label: "Issues", icon: "inbox", match: ["Issues", "IssueDetail"] },
	{ name: "Tasks", label: "Tasks", icon: "check-square", match: ["Tasks", "TaskDetail"] },
]

const implementationItems = [
	{ name: "ImplementationsHub", label: "Overview", icon: "grid", match: ["ImplementationsHub"] },
	{
		name: "WeeklyMonitoring",
		label: "Weekly Monitoring",
		icon: "calendar",
		match: ["WeeklyMonitoring", "WeeklyMonitoringDetail"],
	},
]

const implementationsGroupActive = computed(() =>
	implementationItems.some((item) => item.match.includes(route.name))
)

function isActive(item) {
	return item.match.includes(route.name)
}

function navClass(item, child = false) {
	if (isActive(item)) return activeClass
	if (child) return `font-normal ${inactiveClass}`
	return inactiveClass
}

function toggle() {
	collapsed.value = !collapsed.value
	try {
		localStorage.setItem(STORAGE_KEY, collapsed.value ? "1" : "0")
	} catch (e) {
		/* ignore */
	}
}

function toggleImplementations() {
	if (collapsed.value) {
		collapsed.value = false
		try {
			localStorage.setItem(STORAGE_KEY, "0")
		} catch (e) {
			/* ignore */
		}
	}
	implementationsOpen.value = !implementationsOpen.value
	try {
		localStorage.setItem(IMPL_NAV_KEY, implementationsOpen.value ? "1" : "0")
	} catch (e) {
		/* ignore */
	}
}

watch(
	() => route.name,
	(name) => {
		if (implementationItems.some((item) => item.match.includes(name))) {
			implementationsOpen.value = true
		}
	},
	{ immediate: true }
)

onMounted(() => {
	try {
		collapsed.value = localStorage.getItem(STORAGE_KEY) === "1"
		const stored = localStorage.getItem(IMPL_NAV_KEY)
		if (stored !== null) implementationsOpen.value = stored === "1"
	} catch (e) {
		/* ignore */
	}
})
</script>
