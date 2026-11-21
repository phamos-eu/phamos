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
					class="chip-space-chip chip-space-chip--remote absolute flex items-center justify-center"
					:style="chipStyle(other)"
					:title="other.full_name"
					data-testid="other-chip"
				>
					<span class="inline-flex" :style="{ transform: `scale(${chipScale})` }">
						<ChipFigure
							:user="other.user"
							:label="other.full_name"
							:image="other.user_image"
							:moving="Boolean(other.moving)"
						/>
					</span>
				</div>
				<EncounterBubble
					v-for="bubble in bubbleList"
					:key="bubble.user"
					:ref="(el) => setBubbleRef(bubble.user, el)"
					:peer="bubble.peer"
					:me="me.user"
					:messages="bubble.messages"
					:loading="bubble.loading"
					:error="bubble.error"
					:sending="bubble.sending"
					:style="bubbleStyle(bubble)"
					@send="(text, done) => sendMessage(bubble, text, done)"
					@close="closeBubble(bubble.user)"
				/>
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
import { computed, getCurrentInstance, inject, nextTick, onBeforeUnmount, onMounted, reactive, ref } from "vue"
import { call, FeatherIcon } from "frappe-ui"
import ChipFigure from "../components/ChipFigure.vue"
import EncounterBubble from "../components/EncounterBubble.vue"
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
const SPEED = 6.6 // tiles per second (10% up on 6, PM 2026-11-21)
const SHIFT_SPEED = 16.5
// Two chips can't overlap: centres stay at least this far apart (one chip is 0.8 tiles wide).
const MIN_DISTANCE = 0.8
const SAVE_AFTER_MS = 400
// A quick tap (pressed and released before the next frame) still moves this long.
const TAP_SECONDS = 0.05
// The avatar is drawn at 40px and scaled to the tile.
const AVATAR_PX = 40
// Presence (#2055): a heartbeat keeps my chip on everyone's grid; moves go out at most this often.
const HEARTBEAT_MS = 10000
const SEND_MOVE_EVERY_MS = 120
// Another chip's legs kick until this long after its last move arrived.
const REMOTE_MOVING_MS = 250
const API = "phamos.api.chip_space"
// Encounters (#2056): closer than this (centres, tiles) opens the chat; farther than the second
// closes it again, so standing right at the edge does not flicker.
const ENCOUNTER_DISTANCE = 1.2
const PART_DISTANCE = 1.5
const BUBBLE_WIDTH = 288

// The cockpit's realtime socket (as in useUserRealtime); without it the Space still works alone.
const instance = getCurrentInstance()
const socket = instance?.appContext.config.globalProperties.$socket || inject("$socket", null)

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
	if (event.key === "Enter" && focusNearestBubble()) {
		event.preventDefault()
		return
	}
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

// --- Other chips: dummies from the site config and the people who have the page open (#2055).

let presenceTtlMs = 45000
const lastSeen = new Map()
const movingTimers = new Map()

function upsertOther(chip) {
	if (!chip?.user || chip.user === me.value?.user) return
	lastSeen.set(chip.user, Date.now())
	const existing = others.value.find((o) => o.user === chip.user)
	if (existing) Object.assign(existing, chip)
	else others.value.push({ ...chip, moving: false })
}

function onRemoteMove(message) {
	const other = others.value.find((o) => o.user === message?.user)
	// A move from someone not on my grid yet (missed their join): ask for the full picture.
	if (!other) return message?.user && message.user !== me.value?.user ? refreshOthers() : null
	lastSeen.set(other.user, Date.now())
	other.x = message.x
	other.y = message.y
	other.moving = true
	checkEncounters()
	clearTimeout(movingTimers.get(other.user))
	movingTimers.set(
		other.user,
		setTimeout(() => (other.moving = false), REMOTE_MOVING_MS)
	)
}

function onRemoteLeave(message) {
	others.value = others.value.filter((o) => o.dummy || o.user !== message?.user)
	lastSeen.delete(message?.user)
	checkEncounters()
}

// Chips whose heartbeat stopped (tab killed, network gone) fade out after the presence TTL.
function pruneOthers() {
	const now = Date.now()
	others.value = others.value.filter((o) => o.dummy || now - (lastSeen.get(o.user) || 0) < presenceTtlMs)
	checkEncounters()
}

async function refreshOthers() {
	try {
		const data = await call(`${API}.get_space`)
		for (const chip of data.others || []) upsertOther(chip)
	} catch {
		// The next heartbeat or event tries again.
	}
}

// --- Encounters (#2056): one bubble per chip I am standing next to.

const bubbles = reactive({})
const bubbleRefs = {}
// Chats closed with Esc stay closed until the two walk apart (or Enter opens them again).
const dismissed = new Set()
const bubbleList = computed(() => Object.values(bubbles))

function setBubbleRef(user, el) {
	if (el) bubbleRefs[user] = el
	else delete bubbleRefs[user]
}

function bubbleStyle(bubble) {
	const other = others.value.find((o) => o.user === bubble.user)
	if (!other || !me.value) return { display: "none" }
	const t = tile.value
	const gridWidth = t * me.value.cols
	const centreX = ((me.value.x + other.x) / 2 + 0.5) * t
	const left = Math.max(BUBBLE_WIDTH / 2 + 4, Math.min(gridWidth - BUBBLE_WIDTH / 2 - 4, centreX))
	const top = Math.min(me.value.y, other.y)
	// Near the top edge the bubble hangs below the chips instead (their legs need ~0.5 tile).
	if (top < 6) {
		return { left: `${left}px`, top: `${(Math.max(me.value.y, other.y) + 1.6) * t}px`, transform: "translateX(-50%)" }
	}
	return { left: `${left}px`, top: `${(top - 0.1) * t}px`, transform: "translate(-50%, -100%)" }
}

function distanceTo(other) {
	return Math.hypot(other.x - me.value.x, other.y - me.value.y)
}

function checkEncounters() {
	if (!me.value) return
	for (const other of others.value) {
		const distance = distanceTo(other)
		if (distance < ENCOUNTER_DISTANCE && !bubbles[other.user] && !dismissed.has(other.user)) openBubble(other)
		else if (distance > PART_DISTANCE) {
			delete bubbles[other.user]
			dismissed.delete(other.user)
		}
	}
	// Someone who left the page also leaves the chat.
	for (const user of Object.keys(bubbles)) {
		if (!others.value.some((o) => o.user === user)) delete bubbles[user]
	}
}

async function openBubble(other) {
	const bubble = reactive({
		user: other.user,
		peer: { user: other.user, full_name: other.full_name, user_image: other.user_image },
		encounter: null,
		messages: [],
		loading: true,
		error: "",
		sending: false,
	})
	bubbles[other.user] = bubble
	try {
		// The server checks that we really stand together: my latest spot goes first.
		await call(`${API}.move`, { x: round(me.value.x), y: round(me.value.y) })
		const data = await call(`${API}.open_encounter`, { with_user: other.user })
		bubble.encounter = data.encounter
		bubble.messages = data.messages || []
	} catch (e) {
		bubble.error = errorText(e) || __("The chat could not be opened.")
	} finally {
		bubble.loading = false
	}
	// Walked up to someone: the chat has the keyboard right away, and the chip stops.
	if (bubble.encounter && bubbles[other.user] === bubble) {
		releaseAll()
		await nextTick()
		bubbleRefs[other.user]?.focus()
	}
}

// Esc: the chat closes and the keys move the chip again.
function closeBubble(user) {
	delete bubbles[user]
	dismissed.add(user)
	document.activeElement?.blur?.()
}

async function sendMessage(bubble, text, done) {
	if (!bubble.encounter) return
	bubble.sending = true
	try {
		addMessage(bubble, await call(`${API}.send_encounter_message`, { encounter: bubble.encounter, text }))
		done()
	} catch (e) {
		bubble.error = errorText(e) || __("The message could not be sent.")
	} finally {
		bubble.sending = false
	}
}

function addMessage(bubble, message) {
	if (message && !bubble.messages.some((m) => m.name === message.name)) bubble.messages.push(message)
}

function onEncounterMessage(payload) {
	const bubble = Object.values(bubbles).find((b) => b.encounter && b.encounter === payload?.encounter)
	if (bubble) addMessage(bubble, payload.message)
}

// frappe-ui's call() puts the server's frappe.throw texts into error.messages.
function errorText(e) {
	const first = Array.isArray(e?.messages) ? e.messages[0] : ""
	if (!first || typeof first !== "string") return ""
	return new DOMParser().parseFromString(first, "text/html").body.textContent || ""
}

// Enter (while not typing) jumps into the chat of the nearest chip.
function focusNearestBubble() {
	// A chat closed with Esc, with its person still right here: open it again.
	const near = others.value.find((o) => dismissed.has(o.user) && distanceTo(o) < ENCOUNTER_DISTANCE)
	if (near) {
		dismissed.delete(near.user)
		openBubble(near)
		return true
	}
	const open = Object.values(bubbles).filter((b) => b.encounter)
	if (!open.length) return false
	const nearest = open
		.map((b) => [b, others.value.find((o) => o.user === b.user)])
		.filter(([, o]) => o)
		.sort((a, b) => distanceTo(a[1]) - distanceTo(b[1]))[0]
	if (!nearest) return false
	bubbleRefs[nearest[0].user]?.focus()
	return true
}

// --- My presence.

let lastSent = 0
let sendTimer = null

function sendMove() {
	clearTimeout(sendTimer)
	sendTimer = null
	lastSent = performance.now()
	if (!me.value) return
	call(`${API}.move`, { x: round(me.value.x), y: round(me.value.y) }).catch(() => {})
}

// Leading and trailing: the first step goes out at once, the final spot always arrives.
function queueMove() {
	const wait = SEND_MOVE_EVERY_MS - (performance.now() - lastSent)
	if (wait <= 0) sendMove()
	else if (!sendTimer) sendTimer = setTimeout(sendMove, wait)
}

function heartbeat() {
	if (!me.value) return
	call(`${API}.heartbeat`, { x: round(me.value.x), y: round(me.value.y) }).catch(() => {})
	pruneOthers()
}

// On tab close the component never unmounts: tell the server with a request that outlives the page.
function leaveOnPagehide() {
	try {
		fetch(`/api/method/${API}.leave`, {
			method: "POST",
			keepalive: true,
			headers: { "X-Frappe-CSRF-Token": window.csrf_token || "" },
		})
	} catch {
		// The presence TTL removes the chip anyway.
	}
}

const round = (value) => Math.round(value * 100) / 100

const SOCKET_EVENTS = [
	["chip_space_presence", upsertOther],
	["chip_space_move", onRemoteMove],
	["chip_space_leave", onRemoteLeave],
	["chip_space_message", onEncounterMessage],
	// Rejoin after a lost connection: the others may have moved meanwhile.
	["connect", () => (heartbeat(), refreshOthers())],
]

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
		if (sendTimer) sendMove()
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
		queueMove()
		checkEncounters()
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
	const x = round(me.value.x)
	const y = round(me.value.y)
	if (saved && saved.x === x && saved.y === y) return
	try {
		await call(`${API}.save_my_position`, { x, y })
		saved = { x, y }
	} catch {
		// The next move tries again; the chip stays where the user put it meanwhile.
	}
}

let resizeObserver = null
let heartbeatTimer = null
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
	window.addEventListener("pagehide", leaveOnPagehide)
	try {
		const data = await call(`${API}.get_space`)
		me.value = data.me
		saved = { x: me.value.x, y: me.value.y }
		presenceTtlMs = (data.presence_ttl || 45) * 1000
		for (const chip of data.others || []) upsertOther(chip)
	} catch (e) {
		error.value = __("The Space could not be loaded.")
		return
	}
	checkEncounters()
	for (const [event, handler] of SOCKET_EVENTS) socket?.on?.(event, handler)
	heartbeat()
	heartbeatTimer = setInterval(heartbeat, HEARTBEAT_MS)
})

onBeforeUnmount(() => {
	window.removeEventListener("keydown", onKeydown)
	window.removeEventListener("keyup", onKeyup)
	window.removeEventListener("blur", releaseAll)
	window.removeEventListener("pagehide", leaveOnPagehide)
	for (const [event, handler] of SOCKET_EVENTS) socket?.off?.(event, handler)
	clearInterval(heartbeatTimer)
	clearTimeout(sendTimer)
	for (const timer of movingTimers.values()) clearTimeout(timer)
	if (me.value) call(`${API}.leave`).catch(() => {})
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
/* Other chips arrive about 8 times a second: glide between the updates. */
.chip-space-chip--remote {
	transition: transform 130ms linear;
}
@media (prefers-reduced-motion: reduce) {
	.chip-space-chip--remote {
		transition: none;
	}
}
</style>
