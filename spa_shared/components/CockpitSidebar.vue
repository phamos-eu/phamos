<template>
	<aside
		class="flex h-full flex-none flex-col border-r border-gray-200 bg-white transition-[width] dark:border-gray-800 dark:bg-gray-900"
		:class="collapsed ? 'w-14' : 'w-52'"
	>
		<div
			class="flex h-12 flex-shrink-0 items-center border-b border-gray-200 px-3 dark:border-gray-800"
			:class="collapsed ? 'justify-center' : 'justify-between'"
		>
			<span v-if="!collapsed" class="truncate text-sm font-semibold text-gray-900 dark:text-gray-100">
				{{ label }}
			</span>
			<button
				type="button"
				class="rounded p-1.5 text-gray-500 hover:bg-gray-100 hover:text-gray-800 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-200"
				:title="collapsed ? 'Expand' : 'Collapse'"
				@click="toggle"
			>
				<FeatherIcon :name="collapsed ? 'chevrons-right' : 'chevrons-left'" class="h-4 w-4" />
			</button>
		</div>

		<nav class="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto p-2">
			<template v-for="item in items" :key="item.name">
				<div>
					<router-link
						:to="{ name: item.name }"
						class="flex items-center gap-2 rounded-md px-2 py-2 text-sm font-medium transition"
						:class="
							isActive(item)
								? 'bg-gray-900 text-white dark:bg-gray-100 dark:text-gray-900'
								: 'text-gray-600 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-100'
						"
						:title="collapsed ? item.label : undefined"
					>
						<FeatherIcon :name="item.icon" class="h-4 w-4 flex-shrink-0" />
						<span v-if="!collapsed" class="min-w-0 flex-1 truncate">{{ item.label }}</span>
						<FeatherIcon
							v-if="!collapsed && item.children?.length"
							:name="isGroupOpen(item) ? 'chevron-down' : 'chevron-right'"
							class="h-3.5 w-3.5 flex-shrink-0 opacity-70"
						/>
					</router-link>

					<div
						v-if="item.children?.length && isGroupOpen(item) && !collapsed"
						class="ml-2 mt-1 flex flex-col gap-1 border-l border-gray-200 pl-2 dark:border-gray-700"
					>
						<router-link
							v-for="child in item.children"
							:key="child.name"
							:to="{ name: child.name }"
							class="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm font-normal transition"
							:class="
								isActive(child)
									? 'bg-gray-900 text-white dark:bg-gray-100 dark:text-gray-900'
									: 'text-gray-600 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-100'
							"
						>
							<FeatherIcon :name="child.icon" class="h-3.5 w-3.5 flex-shrink-0" />
							<span class="truncate">{{ child.label }}</span>
						</router-link>
					</div>
				</div>
			</template>
			<slot :collapsed="collapsed" :expand="expand" />
		</nav>

		<div class="mt-auto flex-shrink-0 border-t border-gray-200 p-2 dark:border-gray-800">
			<button
				type="button"
				class="flex w-full items-center gap-2 rounded-md px-2 py-2 text-sm font-medium text-gray-600 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-100"
				:class="collapsed ? 'justify-center' : ''"
				:title="collapsed ? 'Desk' : undefined"
				@click="goDesk"
			>
				<FeatherIcon name="external-link" class="h-4 w-4 flex-shrink-0" />
				<span v-if="!collapsed" class="truncate">Desk</span>
			</button>
		</div>
	</aside>
</template>

<script setup>
import { onMounted, ref, watch } from "vue"
import { useRoute } from "vue-router"

const props = defineProps({
	label: { type: String, required: true },
	storageKey: { type: String, required: true },
	items: { type: Array, default: () => [] },
})

const route = useRoute()
const collapsed = ref(false)
const openGroups = ref({})

function isActive(item) {
	return (item.match || [item.name]).includes(route.name)
}

function groupRouteNames(item) {
	const names = new Set(item.match || [item.name])
	for (const child of item.children || []) {
		for (const n of child.match || [child.name]) names.add(n)
	}
	return names
}

function isGroupOpen(item) {
	if (!item.children?.length) return false
	if (groupRouteNames(item).has(route.name)) return true
	return !!openGroups.value[item.name]
}

watch(
	() => route.name,
	(name) => {
		for (const item of props.items) {
			if (item.children?.length && groupRouteNames(item).has(name)) {
				openGroups.value = { ...openGroups.value, [item.name]: true }
			}
		}
	},
	{ immediate: true }
)

function goDesk() {
	window.location.href = "/app"
}

function toggle() {
	collapsed.value = !collapsed.value
	try {
		localStorage.setItem(props.storageKey, collapsed.value ? "1" : "0")
	} catch (e) {
		/* ignore */
	}
}

function expand() {
	if (!collapsed.value) return
	collapsed.value = false
	try {
		localStorage.setItem(props.storageKey, "0")
	} catch (e) {
		/* ignore */
	}
}

onMounted(() => {
	try {
		collapsed.value = localStorage.getItem(props.storageKey) === "1"
	} catch (e) {
		/* ignore */
	}
})

defineExpose({ collapsed, expand, toggle })
</script>
