<template>
	<!-- Stage icons for ideas (#1773), drawn in the Feather style of the sidebar icons: 24px grid,
	     2px stroke, round ends, current text colour. Feather itself has no plant shapes. -->
	<svg
		xmlns="http://www.w3.org/2000/svg"
		viewBox="0 0 24 24"
		fill="none"
		stroke="currentColor"
		stroke-width="2"
		stroke-linecap="round"
		stroke-linejoin="round"
		aria-hidden="true"
	>
		<path v-for="(d, i) in PATHS[name] || []" :key="i" :d="d" />
	</svg>
</template>

<script setup>
defineProps({
	/** Seed, Sprout, Seedling, Young plant, Growing, Mature, Harvest or Compost */
	name: { type: String, required: true },
})

const PATHS = {
	// a seed with its seam
	Seed: ["M12 4c4 0 6 4 6 8s-2.5 8-6 8-6-4-6-8 2-8 6-8z", "M12 8c-1.5 2-1.5 6 0 8"],
	// stem with two first leaves
	Sprout: ["M12 21v-9", "M12 14c0-3-2.5-5-6.5-5 0 3 2.5 5 6.5 5z", "M12 12c0-3.5 2.5-6 6.5-6 0 3.5-2.5 6-6.5 6z"],
	// a single leaf with its vein
	Seedling: ["M5 19C5 11 10 5 19 5c0 9-6 14-14 14z", "M5 19l8-8"],
	// a plant in a pot
	"Young plant": [
		"M7 15h10l-1.5 6h-7z",
		"M12 15V9",
		"M12 11c-3 0-5-2-5-5 3 0 5 2 5 5z",
		"M12 9c0-3 2-5 5-5 0 3-2 5-5 5z",
	],
	// a tree
	Growing: ["M12 22v-7", "M8 15a4 4 0 0 1-1-7.9 5 5 0 0 1 10 0A4 4 0 0 1 16 15z", "M12 18.5l2.5-2.5"],
	// a ripe apple
	Mature: [
		"M12 8c-2-1.5-7-1.5-7 4.5 0 4 3 8.5 5 8.5 1 0 1.5-.5 2-.5s1 .5 2 .5c2 0 5-4.5 5-8.5C19 6.5 14 6.5 12 8z",
		"M12 8c0-2 1-3.5 3-4.5",
	],
	// a basket
	Harvest: ["M4 10h16l-2 10H6z", "M8 10l4-6 4 6", "M10 13.5v3", "M14 13.5v3"],
	// a heap with a fallen leaf
	Compost: ["M3 20h18", "M5.5 20c1-3.5 3.5-5.5 6.5-5.5s5.5 2 6.5 5.5", "M10 11c0-3 2-5 5-5 0 3-2 5-5 5z"],
}
</script>
