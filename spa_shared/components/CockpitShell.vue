<template>
	<div class="flex h-full min-h-0 bg-surface-gray-1 text-ink-gray-9">
		<slot name="sidebar" />
		<div class="flex min-w-0 flex-1 flex-col">
			<header
				class="flex h-12 flex-shrink-0 items-center border-b border-outline-gray-2 bg-surface-gray-1 px-5"
			>
				<div class="min-w-0 flex-1">
					<div id="cockpit-page-chrome" class="min-w-0" />
					<template v-if="!pageChrome.active">
						<div class="truncate text-base font-semibold tracking-tight text-ink-gray-9">
							{{ title }}
						</div>
					</template>
				</div>
			</header>
			<main class="min-h-0 flex-1 overflow-hidden bg-surface-gray-1">
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
