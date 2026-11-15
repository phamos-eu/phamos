<template>
	<!-- complementary, not dialog: utils/shortcuts.js pauses the cockpit shortcuts while a
	     [role="dialog"] is in the page, and a panel is part of the page. -->
	<section
		v-show="!hidden"
		role="complementary"
		:aria-label="title"
		class="border-b border-outline-gray-2 last:border-b-0"
		:class="fills ? 'flex min-h-0 flex-1 flex-col' : 'flex-none'"
	>
		<div class="group flex items-center gap-1 px-3 py-1.5">
			<button
				type="button"
				class="flex min-w-0 flex-1 items-center gap-2 rounded-md px-1 py-1 text-left hover:bg-surface-gray-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
				:aria-expanded="expanded"
				:aria-controls="bodyId"
				@click="$emit('toggle')"
			>
				<FeatherIcon
					:name="expanded ? 'chevron-down' : 'chevron-right'"
					class="h-4 w-4 flex-shrink-0 text-ink-gray-5"
				/>
				<FeatherIcon
					v-if="typeof panel.icon === 'string'"
					:name="panel.icon"
					class="h-4 w-4 flex-shrink-0 text-ink-gray-6"
				/>
				<component :is="panel.icon" v-else-if="panel.icon" size="md" class="flex-shrink-0" />
				<span class="flex-shrink-0 text-[11px] font-semibold uppercase tracking-wide text-ink-gray-6">
					{{ title }}
				</span>
				<span v-if="summaryText" class="min-w-0 truncate text-xs text-ink-gray-5">· {{ summaryText }}</span>
			</button>
			<div
				v-if="canMoveUp || canMoveDown"
				class="flex flex-shrink-0 opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100"
			>
				<Button
					v-if="canMoveUp"
					variant="ghost"
					size="sm"
					icon="arrow-up"
					:label="__('Move up')"
					:title="__('Move up')"
					@click="$emit('move', -1)"
				/>
				<Button
					v-if="canMoveDown"
					variant="ghost"
					size="sm"
					icon="arrow-down"
					:label="__('Move down')"
					:title="__('Move down')"
					@click="$emit('move', 1)"
				/>
			</div>
		</div>
		<!-- Kept mounted while collapsed: the body loads its data and reports the summary the
		     collapsed row shows (e.g. "1 open · 3/7 done"). -->
		<div
			v-show="expanded"
			:id="bodyId"
			:class="[
				panel.fill ? 'flex min-h-0 flex-1 flex-col' : 'px-4 pb-4 pt-1',
				constrained ? 'max-h-[20vh] overflow-y-auto' : '',
			]"
		>
			<component
				:is="panel.component"
				:key="panel.persistent ? panel.id : record.name"
				v-bind="bodyProps"
				embedded
				@state="onState"
			/>
		</div>
	</section>
</template>

<script setup>
import { computed, provide, ref, watch } from "vue"
import { Button, FeatherIcon } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"

const props = defineProps({
	panel: { type: Object, required: true },
	record: { type: Object, required: true },
	bodyProps: { type: Object, default: () => ({}) },
	expanded: { type: Boolean, default: false },
	canMoveUp: { type: Boolean, default: false },
	canMoveDown: { type: Boolean, default: false },
	// Next to an expanded filling panel (the chat): this body scrolls on its own, capped.
	constrained: { type: Boolean, default: false },
})

const emit = defineEmits(["toggle", "move", "hidden"])

// A body can ask whether it is shown, e.g. the chat lays its Raven frame only while expanded.
provide(
	"dockPanelExpanded",
	computed(() => props.expanded)
)

const title = computed(() => __(props.panel.title))
const bodyId = computed(() => `dock-panel-${props.panel.id}`)

// What the body last reported. The body is keyed by the record, so another record remounts it
// and it reports afresh; a persistent body reports again when its props change.
const reported = ref({})

const hidden = computed(() => !!reported.value.hidden)
const fills = computed(() => props.panel.fill && props.expanded && !hidden.value)
watch(hidden, (value) => emit("hidden", value))

const summaryText = computed(() => {
	if (props.panel.summary) {
		try {
			return props.panel.summary(props.record) || ""
		} catch (e) {
			return ""
		}
	}
	return reported.value.summary || ""
})

function onState(state) {
	reported.value = { ...(state || {}) }
}
</script>
