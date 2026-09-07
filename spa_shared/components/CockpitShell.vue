<template>
	<div class="flex h-full min-h-0 bg-gray-50 text-gray-900 dark:bg-gray-950 dark:text-gray-100">
		<slot name="sidebar" />
		<div class="flex min-w-0 flex-1 flex-col">
			<header
				class="flex h-12 flex-shrink-0 items-center border-b border-gray-200 bg-white px-5 dark:border-gray-800 dark:bg-gray-900"
			>
				<div class="min-w-0 flex-1">
					<div id="cockpit-page-chrome" class="min-w-0" />
					<template v-if="!pageChrome.active">
						<div class="truncate text-base font-semibold tracking-tight text-gray-900 dark:text-gray-100">
							{{ title }}
						</div>
					</template>
				</div>
			</header>
			<main class="min-h-0 flex-1 overflow-hidden">
				<router-view />
			</main>
		</div>
	</div>
</template>

<script setup>
import { pageChrome } from "@spa/pageChrome.js"

defineProps({
	title: { type: String, default: "" },
	subtitle: { type: String, default: "" },
})
</script>
