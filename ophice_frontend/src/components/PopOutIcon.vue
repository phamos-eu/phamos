<template>
	<!--
		Picture-in-picture, "pop out" (PM, 2026-11-22): a screen with a small window in its corner and an arrow breaking in through its top left corner, the
		symbol Chrome shows on its own floating window. Feather has none; drawn in Feather's style.
	-->
	<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
		<!-- The screen, open at its top left corner, where the arrow comes in. -->
		<path d="M10 4h10a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-6" />
		<rect x="12.5" y="12" width="6.5" height="5" rx="1" fill="currentColor" stroke-width="1.5" />
		<!-- The arrow: from outside, through the open corner, into the small window that stays on top. -->
		<line x1="2" y1="2" x2="10" y2="10" />
		<polyline points="10 5 10 10 5 10" />
	</svg>
</template>
