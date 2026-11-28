<template>
	<!-- The team's appointments with its leave and public holidays (#1979), on the shared page. -->
	<AppointmentsPage
		:api="spaConfig.api"
		list-method="get_team_appointments"
		absences-method="get_team_absences"
		view-key="team-appointments-view"
	/>
</template>

<script setup>
import AppointmentsPage from "@spa/views/AppointmentsPage.vue"
import spaConfig from "../config"
</script>
