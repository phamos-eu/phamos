<template>
	<!-- Company appointments (#1949), on the page shared with the Team Cockpit (#1979). -->
	<AppointmentsPage
		:api="spaConfig.api"
		list-method="get_company_appointments"
		view-key="general-management-appointments-view"
	/>
</template>

<script setup>
import AppointmentsPage from "@spa/views/AppointmentsPage.vue"
import spaConfig from "@/config"
</script>
