<template>
	<TodayDashboard :method="`${spaConfig.api}.get_today`" />
</template>

<script setup>
import TodayDashboard from "@spa/components/TodayDashboard.vue"
import spaConfig from "@/config"
</script>
