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
			<div class="ml-auto text-sm text-ink-gray-5">{{ __("Move with WASD or the arrow keys") }}</div>
		</header>

		<div ref="stage" class="flex min-h-0 flex-1 items-center justify-center overflow-hidden p-4">
			<div v-if="me" class="chip-space-grid relative rounded-lg border border-outline-gray-2 bg-surface-white" :style="gridStyle">
				<div
					class="chip-space-chip absolute flex items-center justify-center"
					:style="chipStyle"
					data-testid="my-chip"
				>
					<span class="chip-space-ring inline-flex rounded-full" :style="{ transform: `scale(${chipScale})` }">
						<UserAvatar :name="me.user" :label="me.full_name" :image="me.user_image" size="lg" />
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
import UserAvatar from "@spa/components/UserAvatar.vue"
import { __ } from "@spa/utils/i18n.js"

const MOVES = {
	ArrowUp: [0, -1],
	ArrowDown: [0, 1],
	ArrowLeft: [-1, 0],
	ArrowRight: [1, 0],
	w: [0, -1],
	s: [0, 1],
	a: [-1, 0],
	d: [1, 0],
}
// A held key repeats the move, but not faster than this.
const MOVE_EVERY_MS = 90
const SAVE_AFTER_MS = 400
// The avatar is drawn at 40px and scaled to the tile.
const AVATAR_PX = 40

const stage = ref(null)
const me = ref(null)
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
const chipStyle = computed(() => ({
	width: `${tile.value}px`,
	height: `${tile.value}px`,
	transform: `translate(${me.value.x * tile.value}px, ${me.value.y * tile.value}px)`,
}))

let lastMove = 0
let saveTimer = null
let saved = null

function isTyping(target) {
	if (!target) return false
	const tag = target.tagName
	return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || target.isContentEditable
}

function onKeydown(event) {
	if (!me.value || event.metaKey || event.ctrlKey || event.altKey || isTyping(event.target)) return
	const step = MOVES[event.key.length === 1 ? event.key.toLowerCase() : event.key]
	if (!step) return
	event.preventDefault()
	const now = performance.now()
	if (event.repeat && now - lastMove < MOVE_EVERY_MS) return
	lastMove = now
	const x = Math.max(0, Math.min(me.value.cols - 1, me.value.x + step[0]))
	const y = Math.max(0, Math.min(me.value.rows - 1, me.value.y + step[1]))
	if (x === me.value.x && y === me.value.y) return
	me.value.x = x
	me.value.y = y
	scheduleSave()
}

function scheduleSave() {
	clearTimeout(saveTimer)
	saveTimer = setTimeout(save, SAVE_AFTER_MS)
}

async function save() {
	saveTimer = null
	if (!me.value) return
	const { x, y } = me.value
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
	try {
		me.value = await call("phamos.api.chip_space.get_my_position")
		saved = { x: me.value.x, y: me.value.y }
	} catch (e) {
		error.value = __("The Space could not be loaded.")
	}
})

onBeforeUnmount(() => {
	window.removeEventListener("keydown", onKeydown)
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
	transition: transform 80ms linear;
}
.chip-space-ring {
	box-shadow: 0 0 0 3px var(--surface-white), 0 0 0 5px var(--ink-blue-3, #3b82f6);
}
@media (prefers-reduced-motion: reduce) {
	.chip-space-chip {
		transition: none;
	}
}
</style>
