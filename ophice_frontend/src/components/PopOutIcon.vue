<template>
	<!--
		Picture-in-picture, "pop out" (PM, 2026-11-22): a screen with a small window in its corner and an arrow into it, the
		symbol Chrome shows on its own floating window. Feather has none; drawn in Feather's style.
	-->
	<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
		<rect x="2" y="4" width="20" height="16" rx="2" />
		<rect x="12" y="11.5" width="7" height="5.5" rx="1" fill="currentColor" stroke-width="1.5" />
		<!-- The arrow: out of the page, into the small window that stays on top. -->
		<line x1="5.5" y1="7.5" x2="10" y2="12" />
		<polyline points="10 8.5 10 12 6.5 12" />
	</svg>
</template>
