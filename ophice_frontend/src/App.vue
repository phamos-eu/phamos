<template>
	<!-- Ophice (#2070): one full-screen page; no cockpit shell, no sidebar. -->
	<div class="h-full min-h-0">
		<router-view />
		<Toasts />
	</div>
</template>

<script setup>
import { Toasts } from "frappe-ui"
</script>
