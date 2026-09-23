<template>
	<aside
		class="flex h-full flex-none flex-col border-r border-gray-200 bg-white transition-[width]"
		:class="collapsed ? 'w-14' : 'w-52'"
	>
		<div
			class="flex h-12 flex-shrink-0 items-center border-b border-gray-200 px-3"
			:class="collapsed ? 'justify-center' : 'justify-between'"
		>
			<span v-if="!collapsed" class="truncate text-sm font-semibold text-gray-900">
				I Own My Work
			</span>
			<button
				type="button"
				class="rounded p-1.5 text-gray-500 hover:bg-gray-100 hover:text-gray-800"
				:title="collapsed ? 'Expand' : 'Collapse'"
				@click="toggle"
			>
				<FeatherIcon :name="collapsed ? 'chevrons-right' : 'chevrons-left'" class="h-4 w-4" />
			</button>
		</div>

		<nav class="flex flex-1 flex-col gap-1 p-2">
			<router-link
				v-for="item in items"
				:key="item.name"
				:to="{ name: item.name }"
				class="flex items-center gap-2 rounded-md px-2 py-2 text-sm font-medium transition"
				:class="
					isActive(item)
						? 'bg-gray-900 text-white'
						: 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
				"
				:title="collapsed ? item.label : undefined"
			>
				<FeatherIcon :name="item.icon" class="h-4 w-4 flex-shrink-0" />
				<span v-if="!collapsed" class="truncate">{{ item.label }}</span>
			</router-link>
		</nav>
	</aside>
</template>

<script setup>
import { onMounted, ref } from "vue"
import { useRoute } from "vue-router"

const STORAGE_KEY = "i-own-my-work-sidebar-collapsed"

const route = useRoute()
const collapsed = ref(false)

const items = [
	{ name: "Issues", label: "Issues", icon: "inbox", match: ["Issues", "IssueDetail"] },
	{
		name: "Checklists",
		label: "Checklists",
		icon: "check-square",
		match: ["Checklists", "ChecklistDetail"],
	},
]

function isActive(item) {
	return item.match.includes(route.name)
}

function toggle() {
	collapsed.value = !collapsed.value
	try {
		localStorage.setItem(STORAGE_KEY, collapsed.value ? "1" : "0")
	} catch (e) {
		/* ignore */
	}
}

onMounted(() => {
	try {
		collapsed.value = localStorage.getItem(STORAGE_KEY) === "1"
	} catch (e) {
		/* ignore */
	}
})
</script>
