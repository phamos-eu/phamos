<template>
	<!--
		Shortcut bar (#2073): the cockpits I may open, Personal Cockpit first. Opens them inside
		Ophice. A plain column at the right edge, from the top (PM, 2026-11-22).
	-->
	<nav
		v-if="cockpits.length"
		class="flex w-16 flex-col items-center gap-1.5 overflow-y-auto py-3"
		:aria-label="__('Cockpits')"
		data-testid="cockpit-bar"
	>
		<button
			v-for="(cockpit, index) in cockpits"
			:key="cockpit.route"
			type="button"
			class="cockpit-bar__item group relative flex flex-col items-center rounded-xl p-1"
			:class="{ 'cockpit-bar__item--first': index === 0 }"
			:title="cockpit.title"
			:aria-label="__('Open {0}', [cockpit.title])"
			data-testid="cockpit-shortcut"
			@click="$emit('open', cockpit)"
		>
			<img :src="cockpit.logo" alt="" class="rounded-lg" :class="index === 0 ? 'h-11 w-11' : 'h-9 w-9'" />
			<span v-if="openRoute === cockpit.route" class="absolute -left-0.5 top-1/2 h-1 w-1 -translate-y-1/2 rounded-full bg-ink-gray-7" />
			<span
				class="pointer-events-none absolute right-full top-1/2 mr-2 -translate-y-1/2 whitespace-nowrap rounded bg-black/80 px-2 py-0.5 text-xs text-white opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100"
			>
				{{ cockpit.title }}
			</span>
		</button>
	</nav>
</template>

<script setup>
import { __ } from "@spa/utils/i18n.js"

defineProps({
	/** [{ route, title, logo }] */
	cockpits: { type: Array, default: () => [] },
	/** the cockpit loaded in the frame (a dot under its icon) */
	openRoute: { type: String, default: "" },
})
defineEmits(["open"])
</script>

<style scoped>
.cockpit-bar__item {
	transition: transform 120ms ease-out;
}
.cockpit-bar__item:hover,
.cockpit-bar__item:focus-visible {
	transform: translateX(-3px);
}
</style>
