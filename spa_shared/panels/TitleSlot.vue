<template>
	<!-- A tile's title-bar slot for its panel's own actions (#1917), registered while the tile shows
	     and removed when it goes, so content never teleports into a detached element. -->
	<div ref="el" class="flex min-w-0 flex-shrink items-center" />
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from "vue"
import { panelTitleSlots } from "./hosts.js"

const props = defineProps({ panelId: { type: String, required: true } })
const el = ref(null)

onMounted(() => (panelTitleSlots[props.panelId] = el.value))
onBeforeUnmount(() => {
	if (panelTitleSlots[props.panelId] === el.value) delete panelTitleSlots[props.panelId]
})
</script>
