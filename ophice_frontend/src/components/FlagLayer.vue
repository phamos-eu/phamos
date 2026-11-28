<template>
	<!--
		Flags on the map (#2129, #2130). Everyone's flag with its owner's name on hover. My own: drag
		it to move it, click it for colour, pattern or "Take down". While I aim (placing from the
		sidebar or moving), a see-through flag shows where it lands; on a blocked cell it is crossed out.
	-->
	<div class="pointer-events-none absolute inset-0" data-testid="flag-layer">
		<div
			v-for="flag in flags"
			:key="flag.user"
			class="ophice-flag pointer-events-auto absolute"
			:class="{ 'ophice-flag--mine': flag.user === user, 'ophice-flag--lifted': moving && flag.user === user }"
			:style="cellStyle(flag)"
			data-no-pan
			:data-testid="flag.user === user ? 'my-flag' : 'other-flag'"
			:title="flag.user === user ? __('Your flag: drag it to move it, click it for colour, pattern or to take it down') : __('Flag of {0}', [flag.full_name])"
			@pointerdown="flag.user === user && onDown($event)"
		>
			<FlagIcon :color="flag.color" :pattern="flag.pattern" />
			<span class="ophice-flag__name">{{ flag.user === user ? __("Your flag") : flag.full_name }}</span>
		</div>

		<div v-if="ghost" class="ophice-flag ophice-flag--ghost absolute" :class="{ 'ophice-flag--blocked': ghost.blocked }" :style="cellStyle(ghost)" data-testid="flag-ghost">
			<FlagIcon :color="ghost.color" :pattern="ghost.pattern" />
			<FeatherIcon v-if="ghost.blocked" name="slash" class="ophice-flag__no" />
		</div>

		<!-- My flag's menu -->
		<div
			v-if="menuOpen && mine"
			ref="menu"
			class="ophice-flag-menu pointer-events-auto absolute z-30 w-56 rounded-xl border border-outline-gray-2 bg-surface-white p-2 text-sm text-ink-gray-9 shadow-xl"
			:style="menuStyle"
			data-no-pan
			data-testid="flag-menu"
			@pointerdown.stop
			@click.stop
		>
			<div class="px-1 pb-1 text-xs font-medium text-ink-gray-5">{{ __("Colour") }}</div>
			<div class="grid grid-cols-8 gap-1 px-1 pb-2">
				<button
					v-for="(hue, key) in FLAG_COLORS"
					:key="key"
					type="button"
					class="ophice-flag-menu__swatch"
					:class="{ 'ophice-flag-menu__swatch--on': mine.color === key }"
					:style="{ '--flag-hue': hue }"
					:title="colorNames[key]"
					:aria-label="colorNames[key]"
					:aria-pressed="mine.color === key"
					:data-testid="`flag-color-${key}`"
					@click="$emit('look', { color: key })"
				/>
			</div>
			<div class="px-1 pb-1 text-xs font-medium text-ink-gray-5">{{ __("Pattern") }}</div>
			<div class="grid grid-cols-5 gap-1 px-1 pb-2">
				<button
					v-for="key in FLAG_PATTERNS"
					:key="key"
					type="button"
					class="ophice-flag-menu__pattern"
					:class="{ 'ophice-flag-menu__pattern--on': mine.pattern === key }"
					:title="patternNames[key]"
					:aria-label="patternNames[key]"
					:aria-pressed="mine.pattern === key"
					:data-testid="`flag-pattern-${key}`"
					@click="$emit('look', { pattern: key })"
				>
					<FlagIcon :color="mine.color" :pattern="key" />
				</button>
			</div>
			<button
				type="button"
				class="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left hover:bg-surface-gray-2"
				data-testid="flag-take-down"
				@click="$emit('take-down')"
			>
				<FeatherIcon name="corner-down-left" class="h-4 w-4 text-ink-gray-6" />
				{{ __("Take down") }}
			</button>
			<p class="px-2 pt-0.5 text-xs text-ink-gray-5">{{ __("Back to the sidebar. Drag the flag on the map to move it.") }}</p>
		</div>
	</div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from "vue"
import { FeatherIcon } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"
import FlagIcon from "./FlagIcon.vue"
import { FLAG_COLORS, FLAG_PATTERNS } from "../utils/ophiceFlag.js"

const props = defineProps({
	/** [{ user, full_name, x, y, color, pattern }] */
	flags: { type: Array, default: () => [] },
	tile: { type: Number, required: true },
	/** me */
	user: { type: String, default: "" },
	/** { x, y, color, pattern, blocked } while aiming, or null */
	ghost: { type: Object, default: null },
	menuOpen: { type: Boolean, default: false },
	/** (clientX, clientY) => the cell under that point, or null */
	cellFromPoint: { type: Function, required: true },
})
const emit = defineEmits(["aim", "drop", "menu", "look", "take-down"])

const DRAG_START_PX = 4
const mine = computed(() => props.flags.find((f) => f.user === props.user) || null)
const moving = ref(false)
const menu = ref(null)
let press = null

const colorNames = {
	red: __("Red"),
	orange: __("Orange"),
	amber: __("Amber"),
	green: __("Green"),
	teal: __("Teal"),
	blue: __("Blue"),
	violet: __("Violet"),
	pink: __("Pink"),
}
const patternNames = {
	plain: __("Plain"),
	dots: __("Dots"),
	stripes: __("Stripes"),
	grid: __("Grid"),
	waves: __("Waves"),
}

function cellStyle(cell) {
	return {
		width: `${props.tile}px`,
		height: `${props.tile}px`,
		transform: `translate(${cell.x * props.tile}px, ${cell.y * props.tile}px)`,
	}
}

const menuStyle = computed(() => {
	if (!mine.value) return {}
	return { left: `${(mine.value.x + 1) * props.tile + 6}px`, top: `${mine.value.y * props.tile}px` }
})

// My flag: a press that moves a few pixels is a drag (move the flag), otherwise a click (menu).
function onDown(event) {
	if (event.button !== undefined && event.button !== 0) return
	event.stopPropagation()
	press = { x: event.clientX, y: event.clientY, id: event.pointerId }
	window.addEventListener("pointermove", onMove)
	window.addEventListener("pointerup", onUp)
	window.addEventListener("pointercancel", onCancel)
}

function onMove(event) {
	if (!press || event.pointerId !== press.id) return
	if (!moving.value && Math.hypot(event.clientX - press.x, event.clientY - press.y) < DRAG_START_PX) return
	if (!moving.value) {
		moving.value = true
		emit("menu", false)
	}
	emit("aim", props.cellFromPoint(event.clientX, event.clientY))
}

function onUp(event) {
	if (!press || event.pointerId !== press.id) return
	const wasMoving = moving.value
	stop()
	if (wasMoving) emit("drop", props.cellFromPoint(event.clientX, event.clientY))
	else emit("menu", !props.menuOpen)
}

function onCancel() {
	if (moving.value) emit("aim", null)
	stop()
}

function stop() {
	press = null
	moving.value = false
	window.removeEventListener("pointermove", onMove)
	window.removeEventListener("pointerup", onUp)
	window.removeEventListener("pointercancel", onCancel)
}

// A press outside the open menu (and outside my flag) closes it.
function onOutside(event) {
	if (menu.value?.contains(event.target) || event.target.closest?.("[data-testid=my-flag]")) return
	emit("menu", false)
}
watch(
	() => props.menuOpen,
	(open) => {
		if (open) window.addEventListener("pointerdown", onOutside, true)
		else window.removeEventListener("pointerdown", onOutside, true)
	}
)

onBeforeUnmount(() => {
	stop()
	window.removeEventListener("pointerdown", onOutside, true)
})
</script>

<style scoped>
/* A bit bigger than its cell (PM, 2026-11-27), grown from the foot of the pole so it still
   stands in the cell it was planted on. */
.ophice-flag > .ophice-flag-icon {
	transform: scale(1.4);
	transform-origin: 29% 90%;
}
.ophice-flag--mine {
	cursor: grab;
	touch-action: none;
}
.ophice-flag--lifted {
	opacity: 0.35;
}
/* Above the areas, so a blocked spot inside one shows too. */
.ophice-flag--ghost {
	z-index: 30;
	opacity: 0.75;
	pointer-events: none;
}
.ophice-flag--blocked {
	opacity: 1;
}
.ophice-flag--blocked .ophice-flag-icon {
	opacity: 0.45;
	filter: grayscale(1);
}
.ophice-flag__no {
	position: absolute;
	inset: 15%;
	width: 70%;
	height: 70%;
	color: #dc2626;
	filter: none;
}
.ophice-flag__name {
	position: absolute;
	left: 50%;
	top: 100%;
	transform: translateX(-50%);
	margin-top: 2px;
	white-space: nowrap;
	border-radius: 9999px;
	background: rgb(0 0 0 / 0.72);
	padding: 1px 8px;
	font-size: 11px;
	color: #fff;
	opacity: 0;
	pointer-events: none;
	transition: opacity 120ms ease-out;
}
.ophice-flag:hover .ophice-flag__name {
	opacity: 1;
}
.ophice-flag-menu__swatch {
	height: 1.25rem;
	width: 1.25rem;
	border-radius: 9999px;
	background: hsl(var(--flag-hue) 72% 48%);
	box-shadow: inset 0 0 0 1px hsl(var(--flag-hue) 72% 30%);
}
.ophice-flag-menu__swatch--on {
	outline: 2px solid var(--ink-gray-9);
	outline-offset: 2px;
}
.ophice-flag-menu__pattern {
	height: 2rem;
	border-radius: 0.5rem;
	padding: 0.125rem;
}
.ophice-flag-menu__pattern:hover {
	background: var(--surface-gray-2);
}
.ophice-flag-menu__pattern--on {
	background: var(--surface-gray-3);
}
</style>
