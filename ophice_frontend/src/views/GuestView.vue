<template>
	<!--
		Ophice for guests (#2080, #2082): the public entry at /ophice/guest. A short "I am human"
		check and a name, then the guest is beamed into the guest area. They move only inside it
		and see only it; the rest of the office is blurred. No account, nothing about employees
		elsewhere.
	-->
	<div class="flex h-full min-h-0 flex-col bg-surface-gray-1 text-ink-gray-9" data-testid="guest-view">
		<header class="flex h-12 flex-shrink-0 items-center gap-3 border-b border-outline-gray-2 bg-surface-white px-5">
			<img :src="OPHICE_ICON" alt="" class="h-6 w-6 rounded-md" />
			<span class="text-base font-semibold tracking-tight">{{ __("phamos Ophice") }}</span>
			<span v-if="space" class="ml-auto text-sm text-ink-gray-5">
				{{ __("Move with WASD or the arrow keys") }}
			</span>
		</header>

		<!-- Before coming in: the check and the name. -->
		<main v-if="!space" class="flex min-h-0 flex-1 items-center justify-center overflow-y-auto p-6">
			<div class="w-full max-w-md space-y-5 rounded-2xl border border-outline-gray-2 bg-surface-white p-6 shadow-xl">
				<div class="space-y-1">
					<h1 class="text-xl font-semibold">{{ __("Welcome to the phamos Ophice") }}</h1>
					<p class="text-sm text-ink-gray-6">
						{{ info?.open ? __("Come in and meet us in {0}.", [info.title]) : "" }}
					</p>
				</div>

				<p v-if="info && !info.open" class="rounded-lg bg-surface-amber-1 p-3 text-sm text-ink-amber-4" data-testid="guest-closed">
					{{ __("Nobody can welcome guests at the moment. Please come back later.") }}
				</p>

				<template v-else-if="info">
					<FormControl
						v-model="name"
						:label="__('Your name')"
						:placeholder="__('First and last name')"
						:maxlength="40"
						autocomplete="name"
						data-testid="guest-name"
					/>

					<!-- "I am human": drag the chip through the entrance (#2082). -->
					<div class="space-y-2">
						<p class="text-sm font-medium">{{ __("Drag your chip to the entrance to come in") }}</p>
						<div
							ref="track"
							class="relative h-14 select-none rounded-xl border border-outline-gray-2 bg-surface-gray-2"
							:class="{ 'opacity-50': !canDrag }"
							data-testid="guest-track"
						>
							<!-- The entrance -->
							<div
								v-if="check"
								class="absolute top-1 flex h-12 w-12 -translate-x-1/2 flex-col items-center justify-center rounded-lg border-2 border-dashed border-outline-gray-4 text-ink-gray-5"
								:style="{ left: `${check.door * 100}%` }"
								aria-hidden="true"
							>
								<FeatherIcon name="log-in" class="h-5 w-5" />
							</div>
							<!-- My chip -->
							<button
								type="button"
								class="absolute top-1 flex h-12 w-12 -translate-x-1/2 touch-none items-center justify-center rounded-full bg-surface-gray-7 text-base font-semibold text-ink-white shadow-lg"
								:class="canDrag ? 'cursor-grab active:cursor-grabbing' : 'cursor-not-allowed'"
								:style="{ left: `${dragX * 100}%` }"
								:aria-label="__('Your chip: drag it to the entrance')"
								:disabled="!canDrag"
								data-testid="guest-chip"
								@pointerdown="startDrag"
								@pointermove="moveDrag"
								@pointerup="endDrag"
								@pointercancel="endDrag"
							>
								{{ initials }}
							</button>
						</div>
						<p v-if="!canDrag" class="text-xs text-ink-gray-5">{{ __("Tell us your name first.") }}</p>
					</div>

					<p v-if="error" class="text-sm text-ink-red-4" data-testid="guest-error">{{ error }}</p>
					<p v-if="entering" class="text-sm text-ink-gray-6">{{ __("Coming in…") }}</p>

					<p class="border-t border-outline-gray-1 pt-3 text-xs text-ink-gray-5">
						{{ __("Privacy: we use your name and where your chip stands only for this visit. Chats are not stored for long. Video runs through Jitsi. Your visit ends when you close this page, after 12 hours at the latest.") }}
					</p>
				</template>
				<p v-else class="text-sm text-ink-gray-5">{{ __("Loading…") }}</p>
			</div>
		</main>

		<!-- Inside: the map, sharp only where I may be; the meeting and chat of my area beside it. -->
		<main v-else class="flex min-h-0 flex-1">
		<div ref="stage" class="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden p-4">
			<div class="relative overflow-hidden rounded-lg border border-outline-gray-2 bg-surface-white" :style="gridStyle" data-testid="guest-map">
				<!-- The office, blurred -->
				<div class="guest-map__layer guest-map__layer--blur" aria-hidden="true" />
				<!-- My area, sharp -->
				<div
					v-for="area in space.areas"
					:key="area.name"
					class="guest-map__layer"
					:style="{ clipPath: clipOf(area) }"
					aria-hidden="true"
				/>
				<div
					v-for="area in space.areas"
					:key="`frame-${area.name}`"
					class="absolute rounded-md border-2 border-white/90 shadow-[0_0_14px_rgba(255,255,255,0.7)]"
					:style="rectStyle(area)"
					data-testid="guest-area"
				>
					<span class="absolute -top-6 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-full bg-black/70 px-2 py-0.5 text-xs text-white">
						{{ area.title }}
					</span>
				</div>
				<!-- The people in my area -->
				<div
					v-for="other in space.others"
					:key="other.user"
					class="guest-chip absolute flex items-center justify-center"
					:style="chipStyle(other)"
					:title="other.full_name"
					data-testid="guest-other"
				>
					<span class="inline-flex" :style="{ transform: `scale(${chipScale})` }">
						<ChipFigure :user="other.user" :label="other.full_name" :image="other.user_image" />
					</span>
				</div>
				<div class="guest-chip absolute flex items-center justify-center" :style="chipStyle(me)" :title="me.full_name" data-testid="guest-me">
					<span v-if="beaming" class="guest-beam" aria-hidden="true" />
					<span class="inline-flex" :class="{ 'guest-drop': beaming }" :style="{ '--chip-scale': chipScale, transform: `scale(${chipScale})` }">
						<ChipFigure :user="me.user" :label="me.full_name" ring :moving="moving" />
					</span>
				</div>
			</div>
		</div>
		<!-- The meeting and the guest chat of the area I stand in (#2083). -->
		<aside
			v-if="space.room"
			class="flex w-[380px] flex-shrink-0 flex-col gap-3 border-l border-outline-gray-2 bg-surface-white p-3"
			data-testid="guest-room"
		>
			<div class="overflow-hidden rounded-xl border border-outline-gray-2 bg-black" style="height: 42%">
				<VideoCall
					:key="space.room.area"
					class="h-full"
					fill
					:domain="space.room.jitsi_domain"
					:room="space.room.jitsi_room"
					:display-name="me.full_name"
				/>
			</div>
			<GuestChat
				class="min-h-0 flex-1"
				:title="space.room.title"
				:messages="space.room.messages"
				:me="me.user"
				:on-send="sendChat"
				ophice-path="/ophice/guest"
			/>
		</aside>
		</main>
	</div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from "vue"
import { call, FeatherIcon, FormControl } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"
import ChipFigure from "../components/ChipFigure.vue"
import GuestChat from "../components/GuestChat.vue"
import VideoCall from "../components/VideoCall.vue"

const API = "phamos.api.ophice_guest"
// Served by Frappe, not bundled.
const OPHICE_ICON = "/assets/phamos/manifest/ophice-icon-192.png"
const SPEED = 6.6 // tiles per second, as for employees
const AVATAR_PX = 40
const POLL_MS = 1000
const MOVE_EVERY_MS = 150

const info = ref(null)
const check = ref(null)
const name = ref("")
const error = ref("")
const entering = ref(false)
const space = ref(null)
const me = reactive({ user: "", full_name: "", x: 0, y: 0 })
const moving = ref(false)
const beaming = ref(false)
const stage = ref(null)
const track = ref(null)
const view = reactive({ width: 0, height: 0 })

function errorText(e) {
	return e?.messages?.[0] || e?.message || __("Something went wrong. Please try again.")
}

// --- The check

const dragX = ref(0.04)
const canDrag = computed(() => name.value.trim().length >= 2 && !entering.value && Boolean(check.value))
const initials = computed(
	() =>
		name.value
			.trim()
			.split(/\s+/)
			.map((part) => part[0] || "")
			.join("")
			.slice(0, 2)
			.toUpperCase() || "?"
)
let dragging = false
let path = []
let started = 0

async function newCheck() {
	try {
		check.value = await call(`${API}.start_check`)
	} catch (e) {
		error.value = errorText(e)
	}
	dragX.value = 0.04
}

function trackX(event) {
	const box = track.value.getBoundingClientRect()
	return Math.max(0, Math.min(1, (event.clientX - box.left) / box.width))
}

function startDrag(event) {
	if (!canDrag.value) return
	dragging = true
	started = performance.now()
	path = [[dragX.value, 0]]
	error.value = ""
	event.target.setPointerCapture?.(event.pointerId)
}

function moveDrag(event) {
	if (!dragging) return
	dragX.value = trackX(event)
	path.push([Number(dragX.value.toFixed(4)), Math.round(performance.now() - started)])
}

async function endDrag() {
	if (!dragging) return
	dragging = false
	if (Math.abs(dragX.value - check.value.door) > 0.07) {
		error.value = __("Almost: drop your chip right on the entrance.")
		dragX.value = 0.04
		return
	}
	entering.value = true
	try {
		const data = await call(`${API}.enter`, {
			name: name.value.trim(),
			challenge: check.value.challenge,
			x: dragX.value,
			path: JSON.stringify(path.slice(-200)),
		})
		comeIn(data)
	} catch (e) {
		error.value = errorText(e)
		await newCheck()
	} finally {
		entering.value = false
	}
}

// --- Inside

function comeIn(data) {
	space.value = data
	Object.assign(me, data.me)
	if (data.beam_in) {
		beaming.value = true
		setTimeout(() => (beaming.value = false), 1600)
	}
	nextTick(() => {
		measure()
		resizeObserver?.observe(stage.value)
	})
	startLoops()
}

const tile = computed(() => {
	if (!space.value || !view.width) return 0
	const size = Math.min((view.width - 32) / space.value.cols, (view.height - 32) / space.value.rows)
	return Math.max(8, Math.floor(size))
})
const chipScale = computed(() => (tile.value * 0.8) / AVATAR_PX)

const gridStyle = computed(() => {
	const layout = space.value?.background_layout || { fit: true }
	return {
		width: `${tile.value * (space.value?.cols || 0)}px`,
		height: `${tile.value * (space.value?.rows || 0)}px`,
		"--background-image": space.value?.background ? `url("${encodeURI(space.value.background)}")` : "none",
		"--background-size": layout.fit ? "cover" : `${layout.scale}% auto`,
		"--background-position": layout.fit ? "center" : `${layout.x}% ${layout.y}%`,
	}
})

function rectStyle(area) {
	const t = tile.value
	return { left: `${area.x * t}px`, top: `${area.y * t}px`, width: `${area.width * t}px`, height: `${area.height * t}px` }
}

function clipOf(area) {
	const t = tile.value
	const right = space.value.cols * t - (area.x + area.width) * t
	const bottom = space.value.rows * t - (area.y + area.height) * t
	return `inset(${area.y * t}px ${right}px ${bottom}px ${area.x * t}px round 6px)`
}

function chipStyle(chip) {
	return {
		width: `${tile.value}px`,
		height: `${tile.value}px`,
		transform: `translate(${chip.x * tile.value}px, ${chip.y * tile.value}px)`,
	}
}

/** The nearest spot whose chip centre lies inside one of my areas (the server does the same). */
function clamp(x, y) {
	let best = null
	for (const area of space.value?.areas || []) {
		const cx = Math.min(Math.max(x + 0.5, area.x), area.x + area.width)
		const cy = Math.min(Math.max(y + 0.5, area.y), area.y + area.height)
		const distance = (cx - x - 0.5) ** 2 + (cy - y - 0.5) ** 2
		if (!best || distance < best.distance) best = { distance, x: cx - 0.5, y: cy - 0.5 }
	}
	return best ? { x: best.x, y: best.y } : { x, y }
}

// Keys
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
const held = new Set()
function onKeydown(event) {
	if (!space.value || event.metaKey || event.ctrlKey || event.altKey) return
	if (event.target?.closest?.("input, textarea")) return
	const key = event.key.toLowerCase()
	if (!DIRECTIONS[key]) return
	event.preventDefault()
	held.add(key)
}
function onKeyup(event) {
	held.delete(event.key.toLowerCase())
}

let frame = null
let last = 0
let lastSent = 0
function tickFrame(now) {
	const dt = last ? Math.min(0.05, (now - last) / 1000) : 0
	last = now
	let dx = 0
	let dy = 0
	for (const key of held) {
		dx += DIRECTIONS[key][0]
		dy += DIRECTIONS[key][1]
	}
	const length = Math.hypot(dx, dy)
	moving.value = length > 0
	if (length && dt) {
		const next = clamp(me.x + (dx / length) * SPEED * dt, me.y + (dy / length) * SPEED * dt)
		me.x = next.x
		me.y = next.y
		if (now - lastSent > MOVE_EVERY_MS) {
			lastSent = now
			call(`${API}.guest_move`, { x: me.x, y: me.y }).catch(() => {})
		}
	}
	frame = requestAnimationFrame(tickFrame)
}

/** Write into my area's chat; it shows at once, the next poll brings everyone's. */
async function sendChat(text) {
	const message = await call(`${API}.guest_send`, { text })
	const room = space.value?.room
	if (room && !room.messages.some((m) => m.name === message.name)) room.messages = [...room.messages, message]
}

let pollTimer = null
async function poll() {
	try {
		const data = await call(`${API}.guest_space`)
		space.value = { ...space.value, ...data, me: undefined }
		// The server keeps me inside my areas: follow it when it disagrees (an invite may also widen them).
		if (Math.hypot(data.me.x - me.x, data.me.y - me.y) > 0.75 && !moving.value) {
			me.x = data.me.x
			me.y = data.me.y
		}
	} catch (e) {
		// The visit ended (12 hours, or the session is gone): back to the entrance.
		stopLoops()
		space.value = null
		error.value = errorText(e)
		await newCheck()
	}
}

function startLoops() {
	stopLoops()
	pollTimer = setInterval(poll, POLL_MS)
	frame = requestAnimationFrame(tickFrame)
}
function stopLoops() {
	clearInterval(pollTimer)
	if (frame) cancelAnimationFrame(frame)
	frame = null
}

let resizeObserver = null
function measure() {
	if (!stage.value) return
	view.width = stage.value.clientWidth
	view.height = stage.value.clientHeight
}

function leave() {
	if (!space.value) return
	try {
		fetch(`/api/method/${API}.guest_leave`, {
			method: "POST",
			keepalive: true,
			headers: { "X-Frappe-CSRF-Token": window.csrf_token || "" },
		})
	} catch {
		// the presence TTL removes the chip anyway
	}
}

onMounted(async () => {
	resizeObserver = new ResizeObserver(measure)
	window.addEventListener("keydown", onKeydown)
	window.addEventListener("keyup", onKeyup)
	window.addEventListener("blur", () => held.clear())
	window.addEventListener("pagehide", leave)
	try {
		info.value = await call(`${API}.guest_info`)
	} catch (e) {
		error.value = errorText(e)
		return
	}
	// Still inside from before (reload): straight back in.
	try {
		const data = await call(`${API}.guest_space`)
		comeIn(data)
		return
	} catch {
		// no visit yet
	}
	if (info.value.open) await newCheck()
})

onBeforeUnmount(() => {
	stopLoops()
	resizeObserver?.disconnect()
	window.removeEventListener("keydown", onKeydown)
	window.removeEventListener("keyup", onKeyup)
	window.removeEventListener("pagehide", leave)
})
</script>

<style scoped>
.guest-map__layer {
	position: absolute;
	inset: 0;
	background-image: var(--background-image);
	background-size: var(--background-size, cover);
	background-position: var(--background-position, center);
	background-repeat: no-repeat;
}
/* The office outside my area: blurred and dimmed (#2082). */
.guest-map__layer--blur {
	filter: blur(10px) saturate(0.7) brightness(0.9);
	transform: scale(1.03);
}
.guest-chip {
	top: 0;
	left: 0;
	transition: transform 160ms linear;
	will-change: transform;
}
.guest-beam {
	position: absolute;
	bottom: 30%;
	left: 50%;
	width: 70%;
	height: 900%;
	pointer-events: none;
	border-radius: 999px 999px 40% 40%;
	background: linear-gradient(to top, rgba(255, 255, 255, 0.95), rgba(186, 230, 253, 0.7) 35%, rgba(186, 230, 253, 0));
	box-shadow: 0 0 24px 8px rgba(186, 230, 253, 0.55);
	transform-origin: bottom center;
	animation: guest-beam 1600ms ease-out forwards;
}
@keyframes guest-beam {
	0% { opacity: 0; transform: translateX(-50%) scaleX(0.2) scaleY(0.3); }
	20% { opacity: 1; transform: translateX(-50%) scaleX(1) scaleY(1); }
	100% { opacity: 0; transform: translateX(-50%) scaleX(0.1) scaleY(1); }
}
.guest-drop {
	animation: guest-drop 1100ms cubic-bezier(0.25, 1.4, 0.5, 1) 250ms both;
}
@keyframes guest-drop {
	0% { opacity: 0; transform: translateY(-160%) scale(calc(var(--chip-scale) * 0.4)); }
	100% { opacity: 1; transform: translateY(0) scale(var(--chip-scale)); }
}
@media (prefers-reduced-motion: reduce) {
	.guest-beam,
	.guest-drop {
		animation-duration: 1ms;
	}
}
</style>
