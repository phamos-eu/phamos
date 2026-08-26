<template>
	<nav
		class="fixed bottom-0 inset-x-0 z-40 border-t border-slate-200 bg-white/95 backdrop-blur-sm pb-[env(safe-area-inset-bottom)]"
	>
		<div class="mx-auto flex max-w-lg">
			<router-link
				v-for="item in items"
				:key="item.name"
				:to="item.to"
				class="flex flex-1 flex-col items-center gap-1 py-2.5 text-xs no-underline transition active:opacity-80"
				:class="
					isActive(item.to)
						? 'font-semibold text-slate-900'
						: 'font-medium text-slate-500'
				"
			>
				<span
					class="flex h-9 w-14 items-center justify-center rounded-full"
					:class="isActive(item.to) ? 'bg-slate-900 text-white' : 'bg-transparent'"
				>
					<ion-icon :icon="item.icon" class="text-xl" />
				</span>
				<span>{{ item.label }}</span>
			</router-link>
		</div>
	</nav>
</template>

<script setup>
import { useRoute } from "vue-router"
import { IonIcon } from "@ionic/vue"
import { flagOutline, scanOutline } from "ionicons/icons"

const route = useRoute()

const items = [
	{ name: "Home", label: "Scans", to: "/home", icon: scanOutline },
	{ name: "Issues", label: "Issues", to: "/issues", icon: flagOutline },
]

function isActive(path) {
	return route.path === path || route.path.startsWith(path + "/")
}
</script>
