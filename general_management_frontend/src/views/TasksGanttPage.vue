<template>
	<!-- Tasks Gantt of the General Management Cockpit (#1948): the department's own Tasks, or the
	     top-level Tasks of every cockpit department. -->
	<TasksInbox v-if="scope === 'own'" :key="'own'">
		<template #gantt-toolbar><ScopeToggle v-model="scope" /></template>
	</TasksInbox>
	<CompanyTasksGantt v-else :key="'all'">
		<template #toolbar><ScopeToggle v-model="scope" /></template>
	</CompanyTasksGantt>
</template>

<script setup>
import { ref, watch } from "vue"
import TasksInbox from "@spa/views/TasksInbox.vue"
import CompanyTasksGantt from "./CompanyTasksGantt.vue"
import ScopeToggle from "../components/ScopeToggle.vue"

// The last choice in this browser; the first visit opens on the company view.
const STORAGE_KEY = "general-management-tasks-scope"

function readScope() {
	try {
		return window.localStorage.getItem(STORAGE_KEY) === "own" ? "own" : "all"
	} catch {
		return "all"
	}
}

const scope = ref(readScope())

watch(scope, (value) => {
	try {
		window.localStorage.setItem(STORAGE_KEY, value)
	} catch {
		// Private mode or blocked storage: the choice just isn't remembered.
	}
})
</script>
