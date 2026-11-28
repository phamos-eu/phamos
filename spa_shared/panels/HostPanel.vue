<template>
	<!-- A panel body that is only a place: another component teleports its content here
	     (panels/hosts.js). Persistent, so the element, and with it the teleported content, stays
	     when another record opens or the panel moves between tiles. -->
	<div ref="el" class="flex h-full min-h-0 w-full flex-col" />
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from "vue"
import { panelHosts } from "./hosts.js"

const props = defineProps({
	hostId: { type: String, required: true },
	embedded: { type: Boolean, default: false },
})

const el = ref(null)
onMounted(() => (panelHosts[props.hostId] = el.value))
onBeforeUnmount(() => {
	if (panelHosts[props.hostId] === el.value) delete panelHosts[props.hostId]
})
</script>
