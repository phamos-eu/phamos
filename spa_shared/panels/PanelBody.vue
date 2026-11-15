<template>
	<!-- One panel's body (#1915). Always mounted, whether it shows in a tile or is closed to the
	     rail (PanelLayout parks it), so its rail badge stays current and moving it keeps its state. -->
	<component
		:is="def.component"
		:key="def.persistent ? def.id : record.name"
		v-bind="bodyProps"
		embedded
		@state="(state) => emit('state', state || {})"
	/>
</template>

<script setup>
import { computed, provide } from "vue"
import spaConfig from "@/config"

const props = defineProps({
	def: { type: Object, required: true },
	doctype: { type: String, required: true },
	record: { type: Object, required: true },
	// whether the panel shows in a tile
	open: { type: Boolean, default: false },
})
const emit = defineEmits(["state"])

// A body can ask whether it shows, e.g. the chat lays its Raven frame only then.
provide(
	"dockPanelExpanded",
	computed(() => props.open)
)

const bodyProps = computed(() =>
	props.def.props({ doctype: props.doctype, record: props.record, api: spaConfig.api })
)
</script>
