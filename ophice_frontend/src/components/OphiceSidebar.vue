<template>
	<!--
		Right sidebar (#2073, PM 2026-11-25): the cockpits I may open (Personal Cockpit first; they open
		inside Ophice), my status, and in a section of its own the settings we use while testing
		(text size, meeting areas, background, debug). It replaced the top bar, so the map gets the
		height. Folded it is a column of icons; unfolded it shows the names and what each one does.
		Scrolls when the window is too small. Folded or not is remembered in this browser.
	-->
	<aside
		class="ophice-side flex h-full flex-shrink-0 flex-col overflow-y-auto overflow-x-hidden border-l border-outline-gray-2 bg-surface-white text-ink-gray-9"
		:class="collapsed ? 'w-16 items-center' : 'w-72'"
		:aria-label="__('Ophice')"
		data-testid="ophice-sidebar"
		:data-collapsed="collapsed ? '1' : '0'"
	>
		<!-- Head: unfold / fold -->
		<div class="flex flex-shrink-0 items-center gap-2 pb-1 pt-3" :class="collapsed ? 'justify-center' : 'px-3'">
			<template v-if="!collapsed">
				<img :src="icon" alt="" class="h-6 w-6 rounded-md" />
				<span class="text-sm font-semibold">{{ __("Ophice") }}</span>
			</template>
			<button
				type="button"
				class="ophice-side__icon"
				:class="{ 'ml-auto': !collapsed }"
				:title="collapsed ? __('Unfold the sidebar: names and descriptions') : __('Fold the sidebar to icons')"
				:aria-label="collapsed ? __('Unfold the sidebar: names and descriptions') : __('Fold the sidebar to icons')"
				:aria-expanded="!collapsed"
				data-testid="sidebar-toggle"
				@click="$emit('update:collapsed', !collapsed)"
			>
				<FeatherIcon :name="collapsed ? 'chevrons-left' : 'chevrons-right'" class="h-4 w-4" />
			</button>
		</div>

		<!-- Cockpits -->
		<nav
			v-if="cockpits.length"
			class="flex flex-col gap-1.5 py-2"
			:class="collapsed ? 'items-center' : 'px-2'"
			:aria-label="__('Cockpits')"
			data-testid="cockpit-bar"
		>
			<div v-if="!collapsed" class="ophice-side__title">{{ __("Cockpits") }}</div>
			<button
				v-for="(cockpit, index) in cockpits"
				:key="cockpit.route"
				type="button"
				class="ophice-side__cockpit relative flex items-center gap-3 rounded-xl p-1"
				:class="collapsed ? 'flex-col' : 'hover:bg-surface-gray-2'"
				:title="cockpit.title"
				:aria-label="__('Open {0}', [cockpit.title])"
				data-testid="cockpit-shortcut"
				@click="$emit('open', cockpit)"
			>
				<img :src="cockpit.logo" alt="" class="flex-shrink-0 rounded-lg" :class="index === 0 ? 'h-11 w-11' : 'h-9 w-9'" />
				<span v-if="!collapsed" class="truncate text-sm">{{ cockpit.title }}</span>
				<span v-if="openRoute === cockpit.route" class="absolute -left-0.5 top-1/2 h-1 w-1 -translate-y-1/2 rounded-full bg-ink-gray-7" />
			</button>
		</nav>

		<!-- Me: my status (#2053) -->
		<div class="flex flex-col gap-1 border-t border-outline-gray-2 py-2" :class="collapsed ? 'items-center self-stretch' : 'px-2'">
			<div v-if="!collapsed" class="ophice-side__title">{{ __("You") }}</div>
			<button
				type="button"
				class="ophice-side__row"
				:class="{ 'ophice-side__row--on': statusOpen, 'ophice-side__row--icon': collapsed }"
				:title="__('Set a status: be right back, or away until a time')"
				:aria-label="collapsed ? `${statusLabel}. ${__('Set a status: be right back, or away until a time')}` : undefined"
				data-testid="status-button"
				@click="$emit('status')"
			>
				<FeatherIcon :name="statusIcon" class="h-4 w-4 flex-shrink-0" />
				<span v-if="!collapsed" class="truncate">{{ statusLabel }}</span>
			</button>
			<p v-if="!collapsed" class="ophice-side__hint">{{ __("Be right back, or away until a time. Shown above your chip.") }}</p>
			<!-- My flag (#2130): waits here until I plant it; click then click the map, or drag it there. -->
			<button
				v-if="!flag"
				type="button"
				class="ophice-side__row ophice-side__flag"
				:class="{ 'ophice-side__row--on': placingFlag, 'ophice-side__row--icon': collapsed }"
				draggable="true"
				:title="__('Plant your flag: click it, then click on the map, or drag it onto the map')"
				:aria-label="collapsed ? __('Plant your flag: click it, then click on the map, or drag it onto the map') : undefined"
				:aria-pressed="placingFlag"
				data-testid="flag-button"
				@click="$emit('flag-place')"
				@dragstart="onFlagDragStart"
				@dragend="$emit('flag-drag', false)"
			>
				<span class="h-5 w-5 flex-shrink-0"><FlagIcon :color="flagLook.color" :pattern="flagLook.pattern" /></span>
				<span v-if="!collapsed" class="truncate">{{ placingFlag ? __("Click on the map") : __("Plant your flag") }}</span>
			</button>
			<div
				v-else
				class="ophice-side__row ophice-side__row--static"
				:class="{ 'ophice-side__row--icon': collapsed }"
				:title="__('Your flag is planted. Drag it on the map to move it; click it for colour, pattern or to take it down.')"
				data-testid="flag-planted"
			>
				<span class="h-5 w-5 flex-shrink-0"><FlagIcon :color="flag.color" :pattern="flag.pattern" /></span>
				<span v-if="!collapsed" class="truncate">{{ __("Your flag is planted") }}</span>
			</div>
			<p v-if="!collapsed" class="ophice-side__hint">
				{{ flag ? __("Drag it on the map to move it; click it for colour, pattern or to take it down.") : __("Click it, then click on the map, or drag it onto the map.") }}
			</p>
			<!-- Encounter alert (#2135): asks for browser notifications, mutes chime and notification. -->
			<button
				type="button"
				class="ophice-side__row"
				:class="{ 'ophice-side__row--icon': collapsed }"
				:title="bellTitle"
				:aria-label="collapsed ? bellTitle : undefined"
				:aria-pressed="bell === 'on' || bell === 'blocked'"
				data-testid="encounter-bell"
				@click="$emit('bell')"
			>
				<FeatherIcon :name="bell === 'muted' ? 'bell-off' : 'bell'" class="h-4 w-4 flex-shrink-0" />
				<span v-if="!collapsed" class="truncate">{{ bellLabel }}</span>
			</button>
		</div>

		<!-- Settings we use while testing, a section of their own -->
		<div
			class="flex flex-col gap-1 border-t border-outline-gray-2 py-2"
			:class="collapsed ? 'items-center self-stretch' : 'px-2'"
			data-testid="testing-settings"
		>
			<div v-if="!collapsed" class="ophice-side__title">{{ __("Test settings") }}</div>

			<!-- Text size (#2091) -->
			<div
				class="flex items-center rounded-lg border border-outline-gray-2 p-0.5 text-xs"
				:class="collapsed ? 'flex-col' : 'self-start'"
				:title="__('Text size of Ophice and the cockpits in it')"
				data-testid="text-size"
			>
				<button type="button" class="ophice-zoom__button" :disabled="uiScale <= scales[0]" :title="__('Smaller text')" data-testid="text-smaller" @click="$emit('text-step', -1)">
					<span class="text-[11px] font-semibold">A−</span>
				</button>
				<button type="button" class="ophice-zoom__button tabular-nums text-ink-gray-7" :class="collapsed ? 'w-10 text-[10px]' : 'w-11'" :title="__('Normal text size')" data-testid="text-reset" @click="$emit('text-reset')">
					{{ Math.round(uiScale * 100) }} %
				</button>
				<button type="button" class="ophice-zoom__button" :disabled="uiScale >= scales[scales.length - 1]" :title="__('Larger text')" data-testid="text-larger" @click="$emit('text-step', 1)">
					<span class="text-sm font-semibold">A+</span>
				</button>
			</div>
			<p v-if="!collapsed" class="ophice-side__hint">{{ __("Text size of Ophice and the cockpits in it. The map has its own zoom.") }}</p>

			<template v-if="canEditMap">
				<!-- Meeting areas (#2060, #2071) -->
				<button
					type="button"
					class="ophice-side__row"
					:class="{ 'ophice-side__row--on': editingAreas, 'ophice-side__row--icon': collapsed }"
					:title="__('Draw and edit meeting areas, for everyone')"
					:aria-label="collapsed ? __('Draw and edit meeting areas, for everyone') : undefined"
					:aria-pressed="editingAreas"
					data-testid="areas-button"
					@click="$emit('areas')"
				>
					<FeatherIcon name="video" class="h-4 w-4 flex-shrink-0" />
					<span v-if="!collapsed" class="truncate">{{ editingAreas ? __("Done") : __("Meeting areas") }}</span>
				</button>
				<p v-if="!collapsed" class="ophice-side__hint">{{ __("Drag on the map to draw an area, click an area to edit it. Everyone sees the changes.") }}</p>

				<!-- Background (#2053, #2058, #2089) -->
				<button
					type="button"
					class="ophice-side__row"
					:class="{ 'ophice-side__row--icon': collapsed }"
					:disabled="backgroundBusy"
					:title="__('Upload an image as the background of Ophice, for everyone')"
					:aria-label="collapsed ? __('Upload an image as the background of Ophice, for everyone') : undefined"
					data-testid="background-button"
					@click="$emit('background')"
				>
					<FeatherIcon :name="backgroundBusy ? 'loader' : 'image'" class="h-4 w-4 flex-shrink-0" :class="{ 'animate-spin': backgroundBusy }" />
					<span v-if="!collapsed" class="truncate">{{ __("Background") }}</span>
				</button>
				<p v-if="!collapsed" class="ophice-side__hint">{{ __("Upload an image as the background of Ophice, for everyone.") }}</p>
				<button
					type="button"
					class="ophice-side__row"
					:class="{ 'ophice-side__row--on': adjustingBackground, 'ophice-side__row--icon': collapsed }"
					:title="__('Size and position of the background image on the grid, for everyone')"
					:aria-label="collapsed ? __('Size and position of the background image on the grid, for everyone') : undefined"
					:aria-pressed="adjustingBackground"
					data-testid="adjust-button"
					@click="$emit('adjust')"
				>
					<FeatherIcon name="maximize-2" class="h-4 w-4 flex-shrink-0" />
					<span v-if="!collapsed" class="truncate">{{ __("Adjust") }}</span>
				</button>
				<p v-if="!collapsed" class="ophice-side__hint">{{ __("Size and position of the background image, the grid's size and everyone's starting zoom.") }}</p>
				<template v-if="hasBackground">
					<button
						type="button"
						class="ophice-side__row"
						:class="{ 'ophice-side__row--icon': collapsed }"
						:disabled="backgroundBusy"
						:title="__('Remove the background, for everyone')"
						:aria-label="collapsed ? __('Remove the background, for everyone') : undefined"
						data-testid="remove-background-button"
						@click="$emit('remove-background')"
					>
						<FeatherIcon name="trash-2" class="h-4 w-4 flex-shrink-0" />
						<span v-if="!collapsed" class="truncate">{{ __("Remove background") }}</span>
					</button>
					<p v-if="!collapsed" class="ophice-side__hint">{{ __("Removes the background image, for everyone.") }}</p>
				</template>

				<!-- Debug (#2072): on my own screen only -->
				<Dropdown :options="debugOptions" placement="right">
					<button
						type="button"
						class="ophice-side__row"
						:class="{ 'ophice-side__row--icon': collapsed }"
						:title="__('Debug: simulate things on your own screen only')"
						:aria-label="collapsed ? __('Debug: simulate things on your own screen only') : undefined"
						data-testid="debug-menu"
					>
						<FeatherIcon name="tool" class="h-4 w-4 flex-shrink-0" />
						<span v-if="!collapsed" class="truncate">{{ __("Debug") }}</span>
					</button>
				</Dropdown>
				<p v-if="!collapsed" class="ophice-side__hint">{{ __("Simulate a beam-in or a ping, on your own screen only.") }}</p>
			</template>
		</div>

		<!-- How to move (was in the top bar, #2091) -->
		<div class="mt-auto border-t border-outline-gray-2 py-2" :class="collapsed ? 'flex justify-center self-stretch' : 'px-3'">
			<p v-if="!collapsed" class="ophice-side__hint px-0">{{ moveHint }}</p>
			<span v-else class="ophice-side__icon cursor-help" :title="moveHint" data-testid="move-hint">
				<FeatherIcon name="help-circle" class="h-4 w-4" />
			</span>
		</div>
	</aside>
</template>

<script setup>
import { computed } from "vue"
import { Dropdown, FeatherIcon } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"
import FlagIcon from "./FlagIcon.vue"

const props = defineProps({
	collapsed: { type: Boolean, default: true },
	icon: { type: String, default: "" },
	/** [{ route, title, logo }] */
	cockpits: { type: Array, default: () => [] },
	/** the cockpit loaded in the frame (a dot next to its icon) */
	openRoute: { type: String, default: "" },
	/** my status, or null */
	status: { type: Object, default: null },
	statusOpen: { type: Boolean, default: false },
	uiScale: { type: Number, default: 1 },
	scales: { type: Array, required: true },
	canEditMap: { type: Boolean, default: false },
	editingAreas: { type: Boolean, default: false },
	adjustingBackground: { type: Boolean, default: false },
	hasBackground: { type: Boolean, default: false },
	backgroundBusy: { type: Boolean, default: false },
	debugOptions: { type: Array, default: () => [] },
	/** the encounter alert (#2135): "ask", "on", "blocked" or "muted", and its tooltip */
	bell: { type: String, default: "ask" },
	bellTitle: { type: String, default: "" },
	/** my planted flag (#2130), or null; how it looks while it waits here; placing it right now */
	flag: { type: Object, default: null },
	flagLook: { type: Object, default: () => ({ color: "red", pattern: "plain" }) },
	placingFlag: { type: Boolean, default: false },
})
const emit = defineEmits([
	"update:collapsed",
	"open",
	"status",
	"text-step",
	"text-reset",
	"areas",
	"background",
	"adjust",
	"remove-background",
	"bell",
	"flag-place",
	"flag-drag",
])

const statusIcon = computed(() => (props.status?.kind === "away" ? "moon" : props.status ? "coffee" : "check-circle"))
const statusLabel = computed(() =>
	props.status?.kind === "away" ? __("Away") : props.status ? __("Be right back") : __("Available")
)
const bellLabel = computed(
	() =>
		({
			ask: __("Allow chat notifications"),
			on: __("Chat notifications on"),
			blocked: __("Chat sound on"),
			muted: __("Chat notifications muted"),
		})[props.bell]
)
// Dragging my flag onto the map (#2130): the map takes it on drop.
function onFlagDragStart(event) {
	event.dataTransfer?.setData("text/x-ophice-flag", "1")
	if (event.dataTransfer) event.dataTransfer.effectAllowed = "move"
	emit("flag-drag", true)
}
const moveHint = __("Move with WASD or the arrow keys, Shift to go faster, Space to jump (twice: double jump, hold: fly)")
</script>

<style scoped>
.ophice-side__title {
	padding: 0.25rem 0.5rem;
	font-size: 0.6875rem;
	font-weight: 600;
	letter-spacing: 0.04em;
	text-transform: uppercase;
	color: var(--ink-gray-5);
}
.ophice-side__hint {
	padding: 0 0.5rem 0.375rem;
	font-size: 0.75rem;
	line-height: 1.35;
	color: var(--ink-gray-5);
}
.ophice-side__row {
	display: flex;
	width: 100%;
	align-items: center;
	gap: 0.5rem;
	border-radius: 0.5rem;
	padding: 0.375rem 0.5rem;
	font-size: 0.875rem;
	color: var(--ink-gray-8);
	text-align: left;
}
.ophice-side__row--icon {
	width: auto;
	justify-content: center;
	padding: 0.5rem;
}
.ophice-side__row:hover:not(:disabled) {
	background: var(--surface-gray-2);
	color: var(--ink-gray-9);
}
.ophice-side__row--static:hover:not(:disabled) {
	background: none;
	color: var(--ink-gray-8);
}
.ophice-side__flag {
	cursor: grab;
}
.ophice-side__row:disabled {
	opacity: 0.5;
}
.ophice-side__row--on,
.ophice-side__row--on:hover:not(:disabled) {
	background: var(--surface-gray-7);
	color: var(--ink-white);
}
.ophice-side__icon {
	display: flex;
	align-items: center;
	justify-content: center;
	border-radius: 0.5rem;
	padding: 0.375rem;
	color: var(--ink-gray-6);
}
.ophice-side__icon:hover {
	background: var(--surface-gray-2);
	color: var(--ink-gray-9);
}
.ophice-zoom__button {
	display: flex;
	align-items: center;
	justify-content: center;
	min-width: 1.5rem;
	height: 1.5rem;
	border-radius: 0.375rem;
	color: var(--ink-gray-7);
}
.ophice-zoom__button:hover:not(:disabled) {
	background: var(--surface-gray-2);
	color: var(--ink-gray-9);
}
.ophice-zoom__button:disabled {
	opacity: 0.4;
}
.ophice-side__cockpit {
	transition: transform 120ms ease-out;
}
.ophice-side__cockpit:hover,
.ophice-side__cockpit:focus-visible {
	transform: translateX(-3px);
}
</style>
