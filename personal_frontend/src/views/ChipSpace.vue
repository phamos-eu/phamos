<template>
	<!-- Chip Space (#2053): a full-screen page outside the cockpit shell. -->
	<div class="flex h-full min-h-0 flex-col bg-surface-gray-1 text-ink-gray-9">
		<header class="flex h-12 flex-shrink-0 items-center gap-3 border-b border-outline-gray-2 px-5">
			<router-link
				:to="{ name: 'TodosPlan' }"
				class="inline-flex items-center gap-1.5 rounded px-2 py-1 text-sm text-ink-gray-7 hover:bg-surface-gray-3 hover:text-ink-gray-9"
			>
				<FeatherIcon name="arrow-left" class="h-4 w-4" />
				{{ __("Back to cockpit") }}
			</router-link>
			<div class="text-base font-semibold tracking-tight">{{ __("Space") }}</div>
			<div class="ml-auto text-sm text-ink-gray-5">
				{{ __("Move with WASD or the arrow keys, hold Shift to go faster") }}
			</div>
		</header>

		<div ref="stage" class="flex min-h-0 flex-1 items-center justify-center overflow-hidden p-4">
			<div
				v-if="me"
				class="chip-space-grid relative rounded-lg border border-outline-gray-2 bg-surface-white"
				:style="gridStyle"
			>
				<div
					v-for="other in others"
					:key="other.user"
					class="chip-space-chip absolute flex items-center justify-center"
					:style="chipStyle(other)"
					:title="other.full_name"
					data-testid="other-chip"
				>
					<span class="inline-flex" :style="{ transform: `scale(${chipScale})` }">
						<ChipFigure :user="other.user" :label="other.full_name" :image="other.user_image" />
					</span>
				</div>
				<div
					class="chip-space-chip absolute flex items-center justify-center"
					:style="chipStyle(me)"
					:title="me.full_name"
					data-testid="my-chip"
				>
					<span class="inline-flex" :style="{ transform: `scale(${chipScale})` }">
						<ChipFigure :user="me.user" :label="me.full_name" :image="me.user_image" ring :moving="moving" />
					</span>
				</div>
			</div>
			<div v-else-if="error" class="text-sm text-ink-red-4">{{ error }}</div>
		</div>
	</div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from "vue"
import { call, FeatherIcon } from "frappe-ui"
import ChipFigure from "../components/ChipFigure.vue"
import { __ } from "@spa/utils/i18n.js"

// Positions are in tile units (floats): the grid is drawn, but movement is free.
const DIRECTIONS = {
	arrowup: [0, -1],
	w: [0, -1],
	arrowdown: [0, 1],
	s: [0, 1],
	arrowleft: [-1, 0],
	a: [-1, 0],
	arrowright: [1, 0],
	d: [1, 0],
}
const SPEED = 6 // tiles per second
const SHIFT_SPEED = 15
// Two chips can't overlap: centres stay at least this far apart (one chip is 0.8 tiles wide).
const MIN_DISTANCE = 0.8
const SAVE_AFTER_MS = 400
// A quick tap (pressed and released before the next frame) still moves this long.
const TAP_SECONDS = 0.05
// The avatar is drawn at 40px and scaled to the tile.
const AVATAR_PX = 40

const stage = ref(null)
const me = ref(null)
const others = ref([])
// Drives the kicking legs of my chip.
const moving = ref(false)
const error = ref("")
const view = reactive({ width: 0, height: 0 })

// The largest square tile that fits the whole grid into the page.
const tile = computed(() => {
	if (!me.value || !view.width) return 0
	const size = Math.min((view.width - 32) / me.value.cols, (view.height - 32) / me.value.rows)
	return Math.max(8, Math.floor(size))
})
const chipScale = computed(() => (tile.value * 0.8) / AVATAR_PX)

const gridStyle = computed(() => ({
	width: `${tile.value * me.value.cols}px`,
	height: `${tile.value * me.value.rows}px`,
	"--tile": `${tile.value}px`,
}))
function chipStyle(chip) {
	return {
		width: `${tile.value}px`,
		height: `${tile.value}px`,
		transform: `translate(${chip.x * tile.value}px, ${chip.y * tile.value}px)`,
	}
}

const held = new Set()
// Keys pressed since the last frame: they move once even if already released again.
const tapped = new Set()
let shift = false
let frame = null
let lastTime = 0
let saveTimer = null
let saved = null

function isTyping(target) {
	if (!target) return false
	const tag = target.tagName
	return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || target.isContentEditable
}

function onKeydown(event) {
	shift = event.shiftKey
	if (!me.value || event.metaKey || event.ctrlKey || event.altKey || isTyping(event.target)) return
	const key = event.key.toLowerCase()
	if (!DIRECTIONS[key]) return
	event.preventDefault()
	held.add(key)
	if (!event.repeat) tapped.add(key)
	if (!frame) {
		lastTime = performance.now()
		frame = requestAnimationFrame(tick)
	}
}

function onKeyup(event) {
	shift = event.shiftKey
	// With Shift held, "w" arrives as "W": lower-case both ways.
	held.delete(event.key.toLowerCase())
}

// Leaving the window drops every held key, or the chip would keep sailing.
function releaseAll() {
	held.clear()
	tapped.clear()
	shift = false
}

function blocked(x, y) {
	return others.value.some((o) => Math.hypot(o.x - x, o.y - y) < MIN_DISTANCE)
}

function tick(now) {
	let dt = Math.min(0.05, (now - lastTime) / 1000)
	lastTime = now
	const keys = new Set([...held, ...tapped])
	// Only taps this frame: give them a visible step.
	if (!held.size && tapped.size) dt = TAP_SECONDS
	tapped.clear()
	let dx = 0
	let dy = 0
	for (const key of keys) {
		dx += DIRECTIONS[key][0]
		dy += DIRECTIONS[key][1]
	}
	if (!keys.size || !me.value) {
		frame = null
		moving.value = false
		return
	}
	const length = Math.hypot(dx, dy)
	if (length) {
		// Diagonal moves are not faster than straight ones.
		const step = ((shift ? SHIFT_SPEED : SPEED) * dt) / length
		const maxX = me.value.cols - 1
		const maxY = me.value.rows - 1
		moving.value = true
		const x = Math.max(0, Math.min(maxX, me.value.x + dx * step))
		const y = Math.max(0, Math.min(maxY, me.value.y + dy * step))
		// Each axis on its own, so a chip slides along another one instead of sticking to it.
		if (!blocked(x, me.value.y)) me.value.x = x
		if (!blocked(me.value.x, y)) me.value.y = y
		scheduleSave()
	}
	frame = requestAnimationFrame(tick)
}

function scheduleSave() {
	clearTimeout(saveTimer)
	saveTimer = setTimeout(save, SAVE_AFTER_MS)
}

async function save() {
	saveTimer = null
	if (!me.value) return
	const x = Math.round(me.value.x * 100) / 100
	const y = Math.round(me.value.y * 100) / 100
	if (saved && saved.x === x && saved.y === y) return
	try {
		await call("phamos.api.chip_space.save_my_position", { x, y })
		saved = { x, y }
	} catch {
		// The next move tries again; the chip stays where the user put it meanwhile.
	}
}

let resizeObserver = null
function measure() {
	const el = stage.value
	if (!el) return
	view.width = el.clientWidth
	view.height = el.clientHeight
}

onMounted(async () => {
	measure()
	resizeObserver = new ResizeObserver(measure)
	if (stage.value) resizeObserver.observe(stage.value)
	window.addEventListener("keydown", onKeydown)
	window.addEventListener("keyup", onKeyup)
	window.addEventListener("blur", releaseAll)
	try {
		const data = await call("phamos.api.chip_space.get_space")
		others.value = data.others || []
		me.value = data.me
		saved = { x: me.value.x, y: me.value.y }
	} catch (e) {
		error.value = __("The Space could not be loaded.")
	}
})

onBeforeUnmount(() => {
	window.removeEventListener("keydown", onKeydown)
	window.removeEventListener("keyup", onKeyup)
	window.removeEventListener("blur", releaseAll)
	if (frame) cancelAnimationFrame(frame)
	resizeObserver?.disconnect()
	if (saveTimer) {
		clearTimeout(saveTimer)
		save()
	}
})
</script>

<style scoped>
/* Grid lines from the theme's outline token, so they follow light and dark mode. */
.chip-space-grid {
	background-image: linear-gradient(to right, var(--outline-gray-2) 1px, transparent 1px),
		linear-gradient(to bottom, var(--outline-gray-2) 1px, transparent 1px);
	background-size: var(--tile) var(--tile);
}
.chip-space-chip {
	top: 0;
	left: 0;
	will-change: transform;
}
</style>
