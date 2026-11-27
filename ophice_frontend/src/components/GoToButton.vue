<template>
	<!--
		Go to (PM, 2026-11-22): a click flies my chip there. Pressing ⌘ (Ctrl elsewhere) while the
		pointer is on the button, or a ⌘-click, opens a small menu: Fly or Beam. It stays open while
		⌘ is held, wherever the pointer goes, and folds away when ⌘ is let go (PM, 2026-11-23).
	-->
	<div class="relative inline-flex" @mouseenter="hovered = true" @mouseleave="hovered = false">
		<Button
			size="sm"
			variant="subtle"
			:disabled="disabled"
			:title="__('Fly there. Hold {0} for: Fly or Beam', [modKey])"
			class="whitespace-nowrap"
			data-testid="go-to"
			@focus="focused = true"
			@blur="focused = false"
			@click="onClick"
		>
			<template #prefix><FeatherIcon name="navigation" class="h-3.5 w-3.5" /></template>
			{{ __("Go to") }}
		</Button>
		<div
			v-if="open"
			class="absolute left-0 z-50 w-40 rounded-lg border border-outline-gray-2 bg-surface-white p-1 text-sm text-ink-gray-9 shadow-xl"
			:class="up ? 'bottom-full mb-1' : 'top-full mt-1'"
			role="menu"
			data-testid="go-to-menu"
		>
			<button
				v-for="option in OPTIONS"
				:key="option.mode"
				type="button"
				role="menuitem"
				class="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left hover:bg-surface-gray-2"
				:data-testid="`go-to-${option.mode}`"
				@click="go(option.mode)"
			>
				<FeatherIcon :name="option.icon" class="h-4 w-4 text-ink-gray-6" />
				<span class="flex-1">{{ option.label }}</span>
				<span class="text-xs text-ink-gray-5">{{ option.hint }}</span>
			</button>
		</div>
	</div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue"
import { Button, FeatherIcon } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"

const props = defineProps({
	disabled: { type: Boolean, default: false },
	/** Open the menu above the button (the selection bar sits at the bottom). */
	up: { type: Boolean, default: false },
})
const emit = defineEmits(["go"])

const OPTIONS = [
	{ mode: "fly", icon: "send", label: __("Fly"), hint: __("with wings") },
	{ mode: "beam", icon: "zap", label: __("Beam"), hint: __("at once") },
]
const modKey = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent) ? "⌘" : "Ctrl"

const hovered = ref(false)
const focused = ref(false)
// Opened with ⌘ on the button; open until ⌘ is let go.
const shown = ref(false)
const open = computed(() => !props.disabled && shown.value)

function onKey(event) {
	const held = event.metaKey || event.ctrlKey
	if (!held) shown.value = false
	else if (event.type === "keydown" && (hovered.value || focused.value)) shown.value = true
}
function onBlur() {
	shown.value = false
}
function onClick(event) {
	if (event.metaKey || event.ctrlKey) {
		shown.value = true
		return
	}
	go("fly")
}
function go(mode) {
	shown.value = false
	emit("go", mode)
}

onMounted(() => {
	window.addEventListener("keydown", onKey, true)
	window.addEventListener("keyup", onKey, true)
	window.addEventListener("blur", onBlur)
})
onBeforeUnmount(() => {
	window.removeEventListener("keydown", onKey, true)
	window.removeEventListener("keyup", onKey, true)
	window.removeEventListener("blur", onBlur)
})
</script>
