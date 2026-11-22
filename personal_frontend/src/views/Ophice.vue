<template>
	<!-- Ophice (#2053): a full-screen page outside the cockpit shell. -->
	<div class="flex h-full min-h-0 flex-col bg-surface-gray-1 text-ink-gray-9">
		<header class="flex h-12 flex-shrink-0 items-center gap-3 border-b border-outline-gray-2 px-5">
			<router-link
				:to="{ name: 'TodosPlan' }"
				class="inline-flex items-center gap-1.5 rounded px-2 py-1 text-sm text-ink-gray-7 hover:bg-surface-gray-3 hover:text-ink-gray-9"
			>
				<FeatherIcon name="arrow-left" class="h-4 w-4" />
				{{ __("Back to cockpit") }}
			</router-link>
			<div class="text-base font-semibold tracking-tight">{{ __("Ophice") }}</div>
			<div class="ml-auto text-sm text-ink-gray-5">
				{{ __("Move with WASD or the arrow keys, Shift to go faster, Space to jump (twice: double jump, hold: fly)") }}
			</div>
			<Button
				v-if="me"
				:variant="showPeople ? 'solid' : 'subtle'"
				:title="__('Show or hide the people list')"
				:aria-pressed="showPeople"
				data-testid="people-toggle"
				@click="togglePeople"
			>
				<template #prefix><FeatherIcon name="users" class="h-4 w-4" /></template>
				{{ __("People") }}
			</Button>
			<!-- My status (#2053): be right back / away, shown above my chip. -->
			<Button
				v-if="me"
				:variant="statusOpen ? 'solid' : 'subtle'"
				:title="__('Set a status: be right back, or away until a time')"
				data-testid="status-button"
				@click="statusOpen = !statusOpen"
			>
				<template #prefix>
					<FeatherIcon :name="me.status?.kind === 'away' ? 'moon' : me.status ? 'coffee' : 'check-circle'" class="h-4 w-4" />
				</template>
				{{ me.status?.kind === "away" ? __("Away") : me.status ? __("Be right back") : __("Available") }}
			</Button>
			<!-- Meeting areas (#2060): edit mode = drag to draw, click an area to edit it. -->
			<Button
				v-if="me"
				:variant="editingAreas ? 'solid' : 'subtle'"
				:title="__('Draw and edit meeting areas, for everyone')"
				:aria-pressed="editingAreas"
				@click="editingAreas = !editingAreas"
			>
				<template #prefix><FeatherIcon name="video" class="h-4 w-4" /></template>
				{{ editingAreas ? __("Done") : __("Meeting areas") }}
			</Button>
			<!-- Ophice's background, one for everyone (#2053). -->
			<input
				ref="backgroundInput"
				type="file"
				accept="image/png,image/jpeg,image/webp,image/gif"
				class="hidden"
				@change="uploadBackground"
			/>
			<Button
				v-if="me"
				variant="subtle"
				:loading="backgroundBusy"
				:title="__('Upload an image as the background of Ophice, for everyone')"
				@click="backgroundInput?.click()"
			>
				<template #prefix><FeatherIcon name="image" class="h-4 w-4" /></template>
				{{ __("Background") }}
			</Button>
			<Button
				v-if="me && background"
				:variant="adjustingBackground ? 'solid' : 'subtle'"
				:title="__('Size and position of the background image on the grid, for everyone')"
				:aria-pressed="adjustingBackground"
				@click="adjustingBackground = !adjustingBackground"
			>
				<template #prefix><FeatherIcon name="maximize-2" class="h-4 w-4" /></template>
				{{ __("Adjust") }}
			</Button>
			<Button
				v-if="me && background"
				variant="ghost"
				:disabled="backgroundBusy"
				:title="__('Remove the background, for everyone')"
				@click="removeBackground"
			>
				{{ __("Remove") }}
			</Button>
		</header>

		<div class="flex min-h-0 flex-1">
		<!-- People (#2063): everyone with Raven, online first; click one to chat. -->
		<PeopleSidebar
			v-if="me && showPeople"
			:people="people"
			:me="me.user"
			:hide-details="hideDetails"
			:now="clock"
			@pick="(person, event) => openChatWith(person, event)"
			@hide="setHideDetails"
		/>
		<div ref="stage" class="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden p-4">
			<!-- Size and position of the background image against the grid (#2058), top left. -->
			<div
				v-if="adjustingBackground && background"
				class="absolute left-6 top-6 z-30 w-72 space-y-3 rounded-xl border border-outline-gray-2 bg-surface-white p-3 text-sm text-ink-gray-9 shadow-xl"
				data-testid="background-adjust"
			>
				<div class="flex items-center justify-between">
					<span class="font-medium">{{ __("Background image") }}</span>
					<Button variant="ghost" :disabled="backgroundLayout.fit" @click="setLayout({ fit: true })">
						{{ __("Fit") }}
					</Button>
				</div>
				<label class="block">
					<span class="flex justify-between text-xs text-ink-gray-6">
						<span>{{ __("Size") }}</span><span>{{ backgroundLayout.fit ? __("Fit") : `${backgroundLayout.scale} %` }}</span>
					</span>
					<input
						type="range" min="20" max="300" step="1" class="w-full"
						:value="backgroundLayout.scale"
						data-testid="background-scale"
						@input="setLayout({ fit: false, scale: +$event.target.value })"
					/>
				</label>
				<label class="block">
					<span class="text-xs text-ink-gray-6">{{ __("Horizontal position") }}</span>
					<input
						type="range" min="0" max="100" step="0.5" class="w-full"
						:value="backgroundLayout.x"
						@input="setLayout({ fit: false, x: +$event.target.value })"
					/>
				</label>
				<label class="block">
					<span class="text-xs text-ink-gray-6">{{ __("Vertical position") }}</span>
					<input
						type="range" min="0" max="100" step="0.5" class="w-full"
						:value="backgroundLayout.y"
						@input="setLayout({ fit: false, y: +$event.target.value })"
					/>
				</label>
				<p class="text-xs text-ink-gray-5">{{ __("The grid stays as it is; everyone sees the change.") }}</p>
			</div>
			<!-- The meeting of the area I stand in (#2060), top right. -->
			<!-- Meeting view (#2061): the meeting is the big window, the map shrinks to the bottom left. -->
			<MeetingPanel
				v-if="meetingArea"
				ref="meetingPanel"
				class="z-30"
				:area="meetingArea"
				:display-name="me?.full_name"
				:bounds="view"
				:rect="meetingRect || defaultMeetingRect()"
				@update:rect="setMeetingRect"
				@leave="leaveMeeting(true)"
			/>
			<StatusMenu
				v-if="statusOpen && me"
				class="absolute right-6 top-6 z-40"
				:status="me.status"
				:on-save="saveStatus"
				@close="statusOpen = false"
			/>
			<!-- The area's chat (#2062), above the mini map. -->
			<AreaChat
				v-if="meetingArea && me"
				:key="meetingArea.name"
				class="absolute z-20"
				:style="areaChatStyle"
				:area="meetingArea"
				:me="me.user"
				:name-of="nameOf"
				:socket="socket"
			/>
			<AreaDialog :area="areaDraft" :on-save="saveArea" :on-delete="deleteArea" @close="areaDraft = null" />
			<p
				v-if="editingAreas"
				class="pointer-events-none absolute left-1/2 top-3 z-30 -translate-x-1/2 rounded-full bg-black/75 px-3 py-1 text-xs text-white"
			>
				{{ __("Drag on the grid to mark a meeting area, click an area to edit it") }}
			</p>
			<!-- Burn notices (#2057): bottom centre, above the grid. -->
			<div
				v-if="noticeList.length"
				class="pointer-events-none absolute inset-x-0 bottom-6 z-30 flex flex-col items-center gap-2"
			>
				<BurnNotice
					v-for="notice in noticeList"
					:key="notice.encounter"
					class="pointer-events-auto"
					:notice="notice"
					:now="now"
					:saving="notice.saving"
					@save="saveEncounter(notice)"
				/>
			</div>
			<div
				v-if="me"
				class="ophice-grid rounded-lg border border-outline-gray-2 bg-surface-white"
				:class="{
					'ophice-grid--image': background,
					relative: !meetingArea,
					'ophice-grid--mini absolute z-20 shadow-xl': meetingArea,
				}"
				:style="gridStyle"
			>
				<AreaLayer
					:areas="areas"
					:tile="tile"
					:cols="me.cols"
					:rows="me.rows"
					:editing="editingAreas"
					:active-name="meetingArea?.name || ''"
					@draw="(rect) => (areaDraft = { ...rect })"
					@pick="(area) => (areaDraft = { ...area })"
				/>
				<!-- Perimeters (#2056): touching circles = in conversation. Below the chips, no clicks. -->
				<div
					v-for="chip in perimeterList"
					:key="`perimeter-${chip.user}`"
					class="ophice-perimeter pointer-events-none absolute rounded-full"
					:class="{
						'ophice-perimeter--me': chip.mine,
						'ophice-perimeter--contact': chip.contact,
						'ophice-chip--remote': !chip.mine,
					}"
					:style="perimeterStyle(chip)"
					:data-testid="chip.mine ? 'my-perimeter' : 'other-perimeter'"
					:data-contact="chip.contact ? '1' : '0'"
				/>
				<div
					v-for="other in others"
					:key="other.user"
					class="ophice-chip ophice-chip--remote absolute flex cursor-pointer items-center justify-center"
					:style="chipStyle(other)"
					@click="openChatWith(other, $event)"
					:title="other.offline ? __('{0} (away, page closed)', [other.full_name]) : other.full_name"
					data-testid="other-chip"
				>
					<span class="inline-flex" :style="{ transform: `scale(${chipScale})` }">
						<ChipFigure
							:user="other.user"
							:label="other.full_name"
							:image="other.user_image"
							:moving="Boolean(other.moving)"
							:offline="Boolean(other.offline)"
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
					:video="bubble.user === videoUser ? bubble.video : null"
					:display-name="me.full_name"
					:style="bubbleStyle(bubble)"
					@send="(text, done) => sendMessage(bubble, text, done)"
					@close="closeBubble(bubble.user)"
				/>
				<div
					class="ophice-chip absolute flex items-center justify-center"
					:style="chipStyle(me)"
					:title="me.full_name"
					data-testid="my-chip"
				>
					<span class="inline-flex" :style="{ transform: `scale(${chipScale})` }">
						<ChipFigure
							:user="me.user"
							:label="me.full_name"
							:image="me.user_image"
							ring
							:moving="moving"
							:jumping="jumping"
							:double-jump="doubleJumped"
							:flying="flying"
						/>
					</span>
				</div>
				<!-- Statuses float above their chips, under the chat bubbles. -->
				<StatusTag
					v-for="chip in statusChips"
					:key="`status-${chip.user}`"
					:status="chip.status"
					:now="clock"
					:style="tagStyle(chip)"
					:class="{ 'ophice-chip--remote': chip.user !== me.user }"
				/>
			</div>
			<div v-else-if="error" class="text-sm text-ink-red-4">{{ error }}</div>
		</div>
		</div>
		<ChatWithMenu v-if="chatWith" :key="chatWith.person.user" :person="chatWith.person" :at="chatWith.at" @close="chatWith = null" />
	</div>
</template>

<script setup>
import { computed, getCurrentInstance, inject, nextTick, onBeforeUnmount, onMounted, reactive, ref } from "vue"
import { Button, call, FeatherIcon, toast } from "frappe-ui"
import ChipFigure from "../components/ChipFigure.vue"
import EncounterBubble from "../components/EncounterBubble.vue"
import BurnNotice from "../components/BurnNotice.vue"
import AreaLayer from "../components/AreaLayer.vue"
import AreaDialog from "../components/AreaDialog.vue"
import MeetingPanel from "../components/MeetingPanel.vue"
import AreaChat from "../components/AreaChat.vue"
import PeopleSidebar from "../components/PeopleSidebar.vue"
import ChatWithMenu from "../components/ChatWithMenu.vue"
import StatusTag from "../components/StatusTag.vue"
import StatusMenu from "../components/StatusMenu.vue"
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
const API = "phamos.api.ophice"
// Encounters (#2056): closer than this (centres, tiles) opens the chat; farther than the second
// closes it again, so standing right at the edge does not flicker.
// Each chip's perimeter has half the encounter distance as radius: two touching circles = in range.
const ENCOUNTER_DISTANCE = 2
const PART_DISTANCE = 2.4
const PERIMETER_RADIUS = ENCOUNTER_DISTANCE / 2
const BUBBLE_WIDTH = 288
const BUBBLE_WIDTH_VIDEO = 384

// The cockpit's realtime socket (as in useUserRealtime); without it Ophice still works alone.
const instance = getCurrentInstance()
const socket = instance?.appContext.config.globalProperties.$socket || inject("$socket", null)

const stage = ref(null)
const me = ref(null)
const others = ref([])
// Drives the kicking legs of my chip.
const moving = ref(false)
const error = ref("")
const view = reactive({ width: 0, height: 0 })

// The largest square tile that fits the whole grid into the page; in a meeting (#2061) into
// the mini map at the bottom left.
const MINI_SHARE = 0.3
const MINI_MIN = 260
const MINI_MAX = 440
const STAGE_PAD = 16
const miniWidth = computed(() => Math.max(MINI_MIN, Math.min(MINI_MAX, view.width * MINI_SHARE)))
const tile = computed(() => {
	if (!me.value || !view.width) return 0
	if (meetingArea.value) return Math.max(4, Math.floor(miniWidth.value / me.value.cols))
	const size = Math.min((view.width - 32) / me.value.cols, (view.height - 32) / me.value.rows)
	return Math.max(8, Math.floor(size))
})

// Where the meeting window sits, as shares of the stage (they follow the window size); the
// user's own placement is kept in this browser.
const MEETING_RECT_KEY = "phamos_ophice_meeting_rect"
function defaultMeetingRect() {
	const width = view.width || 1200
	const height = view.height || 800
	const left = miniWidth.value + STAGE_PAD * 2
	return {
		x: left / width,
		y: STAGE_PAD / height,
		w: (width - left - STAGE_PAD) / width,
		h: (height - STAGE_PAD * 2) / height,
	}
}
function storedMeetingRect() {
	try {
		const rect = JSON.parse(localStorage.getItem(MEETING_RECT_KEY) || "null")
		const ok = rect && ["x", "y", "w", "h"].every((k) => Number.isFinite(rect[k]) && rect[k] >= 0 && rect[k] <= 1)
		return ok ? rect : null
	} catch {
		return null
	}
}
const meetingRect = ref(storedMeetingRect())
const meetingPanel = ref(null)
function setMeetingRect(rect) {
	meetingRect.value = rect
	try {
		localStorage.setItem(MEETING_RECT_KEY, JSON.stringify(rect))
	} catch {
		// private window: the placement lasts until the reload
	}
}
const chipScale = computed(() => (tile.value * 0.8) / AVATAR_PX)

const gridStyle = computed(() => ({
	width: `${tile.value * me.value.cols}px`,
	height: `${tile.value * me.value.rows}px`,
	...(meetingArea.value ? { left: `${STAGE_PAD}px`, bottom: `${STAGE_PAD}px` } : {}),
	"--tile": `${tile.value}px`,
	// The grid lines stay on top of the image (see .ophice-grid--image).
	"--background-image": background.value ? `url("${encodeURI(background.value)}")` : "none",
	// Size in % of the grid width, position in %: the map can be spaced against the grid.
	"--background-size": backgroundLayout.value.fit ? "cover" : `${backgroundLayout.value.scale}% auto`,
	"--background-position": backgroundLayout.value.fit
		? "center"
		: `${backgroundLayout.value.x}% ${backgroundLayout.value.y}%`,
}))

// --- Background image (one for everyone, anyone may change it).

const background = ref("")
const FITTED = { fit: true, scale: 100, x: 50, y: 50 }
const backgroundLayout = ref({ ...FITTED })
const adjustingBackground = ref(false)
let layoutTimer = null

// Live for me while dragging; saved (and sent to everyone) a moment after the last change.
function setLayout(change) {
	backgroundLayout.value = change.fit ? { ...FITTED } : { ...backgroundLayout.value, ...change, fit: false }
	clearTimeout(layoutTimer)
	layoutTimer = setTimeout(async () => {
		const { fit, scale, x, y } = backgroundLayout.value
		try {
			await call(`${API}.set_background_layout`, { fit: fit ? 1 : 0, scale, x, y })
		} catch (e) {
			toast.error(errorText(e) || __("The background could not be adjusted."))
		} finally {
			layoutTimer = null
		}
	}, 300)
}
const backgroundInput = ref(null)
const backgroundBusy = ref(false)

async function uploadBackground(event) {
	const file = event.target.files?.[0]
	event.target.value = ""
	if (!file) return
	backgroundBusy.value = true
	try {
		const form = new FormData()
		form.append("file", file, file.name)
		const response = await fetch(`/api/method/${API}.upload_background`, {
			method: "POST",
			body: form,
			headers: { "X-Frappe-CSRF-Token": window.csrf_token || "" },
		})
		const data = await response.json().catch(() => ({}))
		if (!response.ok) throw { messages: serverMessages(data) }
		background.value = data.message?.url || ""
	} catch (e) {
		toast.error(errorText(e) || __("The image could not be uploaded."))
	} finally {
		backgroundBusy.value = false
	}
}

async function removeBackground() {
	backgroundBusy.value = true
	try {
		await call(`${API}.remove_background`)
		background.value = ""
	} catch (e) {
		toast.error(errorText(e) || __("The background could not be removed."))
	} finally {
		backgroundBusy.value = false
	}
}

function serverMessages(data) {
	try {
		return JSON.parse(data._server_messages || "[]").map((m) => JSON.parse(m).message)
	} catch {
		return []
	}
}
// Every chip with its perimeter; "contact" when it touches another one (anyone's, so groups
// show as touching circles too).
const perimeterList = computed(() => {
	if (!me.value) return []
	const chips = [{ ...me.value, mine: true }, ...others.value.map((o) => ({ ...o, mine: false }))]
	return chips.map((chip) => ({
		user: chip.user,
		x: chip.x,
		y: chip.y,
		mine: chip.mine,
		contact: chips.some((o) => o.user !== chip.user && Math.hypot(o.x - chip.x, o.y - chip.y) < ENCOUNTER_DISTANCE),
	}))
})

function perimeterStyle(chip) {
	const size = PERIMETER_RADIUS * 2 * tile.value
	// Centred on the chip's tile centre.
	const offset = (0.5 - PERIMETER_RADIUS) * tile.value
	return {
		width: `${size}px`,
		height: `${size}px`,
		transform: `translate(${chip.x * tile.value + offset}px, ${chip.y * tile.value + offset}px)`,
	}
}

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
	if (event.key === "Escape" && meetingArea.value && !Object.keys(bubbles).length && !document.fullscreenElement) {
		event.preventDefault()
		if (!meetingPanel.value?.exitFill()) leaveMeeting(true)
		return
	}
	if (!held.size && !event.repeat) {
		// Typed while the chat that just opened is still loading: keep it for the chat.
		if (bufferWhileOpening(event)) return
		// Esc said "walk on"; Enter brings the chat back while still next to the person.
		if (event.key === "Enter" && reopenDismissed()) {
			event.preventDefault()
			return
		}
	}
	// Space: jump, over other chips, so nobody gets stuck anywhere (PM, 2026-11-22). Again in
	// the air: double jump. Held until landing: hover with wings until it is let go.
	if (event.code === "Space") {
		event.preventDefault()
		spaceHeld = true
		if (event.repeat) return
		backFromStatus()
		if (!jump && !flying.value) startJump()
		else if (jump && !jump.doubled) doubleJump()
		return
	}
	const key = event.key.toLowerCase()
	if (!DIRECTIONS[key]) return
	event.preventDefault()
	backFromStatus()
	held.add(key)
	heldCount.value = held.size
	if (!event.repeat) tapped.add(key)
	if (!frame) {
		lastTime = performance.now()
		frame = requestAnimationFrame(tick)
	}
}

function onKeyup(event) {
	shift = event.shiftKey
	if (event.code === "Space") {
		spaceHeld = false
		if (flying.value) land()
		return
	}
	// With Shift held, "w" arrives as "W": lower-case both ways.
	const wasWalking = held.size > 0
	held.delete(event.key.toLowerCase())
	heldCount.value = held.size
	// Every key let go next to someone: the chat opens and has the keyboard (PM, 2026-11-21).
	// Whoever keeps a key held walks on, also when changing keys with overlap.
	if (wasWalking && !held.size && !flying.value && !jump) chatOnStop()
}

/** The nearest chip within the encounter distance, or null. */
function nearestInRange() {
	let best = null
	for (const other of others.value) {
		if (other.offline) continue
		const distance = distanceTo(other)
		if (distance < ENCOUNTER_DISTANCE && (!best || distance < best.distance)) best = { other, distance }
	}
	return best?.other || null
}

/** Stopped walking: next to someone, the chat opens (or gets the keyboard if already open). */
function chatOnStop() {
	joinAreaIfInside()
	const other = nearestInRange()
	if (!other || dismissed.has(other.user)) return
	const bubble = bubbles[other.user]
	if (!bubble) openBubble(other, { focus: true })
	else if (!bubble.loading) focusBubble(other.user)
	else bubble.focusOnOpen = true
}

function bufferWhileOpening(event) {
	const bubble = Object.values(bubbles).find((b) => b.loading && b.focusOnOpen)
	if (!bubble || event.key.length !== 1) return false
	event.preventDefault()
	bubble.pendingText += event.key
	return true
}

function reopenDismissed() {
	const other = nearestInRange()
	if (!other || !dismissed.has(other.user)) return false
	dismissed.delete(other.user)
	openBubble(other, { focus: true })
	return true
}

// Leaving the window drops every held key, or the chip would keep sailing.
function releaseAll() {
	held.clear()
	heldCount.value = 0
	tapped.clear()
	shift = false
	spaceHeld = false
	if (flying.value) land()
}

// --- Other chips: dummies from the site config and the people who have the page open (#2055).

let presenceTtlMs = 45000
const lastSeen = new Map()
const movingTimers = new Map()

function upsertOther(chip) {
	if (!chip?.user || chip.user === me.value?.user) return
	lastSeen.set(chip.user, Date.now())
	const existing = others.value.find((o) => o.user === chip.user)
	// Away with the page closed (#2053): stays, greyed out; any heartbeat makes it live again.
	const values = { ...chip, offline: Boolean(chip.offline), status: chip.status || null }
	if (existing) Object.assign(existing, values)
	else others.value.push({ ...values, moving: false })
	checkEncounters()
}

const awayOver = (o) => !o.status?.until || Date.parse(o.status.until) + AWAY_GRACE_MS < Date.now()

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
	others.value = others.value.filter((o) => {
		if (o.dummy || now - (lastSeen.get(o.user) || 0) < presenceTtlMs) return true
		// No heartbeat, but away: keep showing them, greyed out, until well after their return time.
		if (o.status?.kind === "away" && !awayOver(o)) return (o.offline = true)
		return false
	})
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
// The open encounter with each chip, also while its bubble is closed (Esc): parting needs it.
const encounterByUser = new Map()
const bubbleList = computed(() => Object.values(bubbles))

// Video (#2059): one call at a time, with the nearest person whose chat is open.
const videoUser = computed(() => {
	// One call at a time: an area's meeting wins over the encounter call (#2060).
	if (!me.value || meetingArea.value) return null
	let best = null
	for (const bubble of Object.values(bubbles)) {
		if (!bubble.video) continue
		const other = others.value.find((o) => o.user === bubble.user)
		if (!other) continue
		const distance = Math.hypot(other.x - me.value.x, other.y - me.value.y)
		if (!best || distance < best.distance) best = { user: bubble.user, distance }
	}
	return best?.user || null
})

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
	// With the video call the bubble is wider and about 200px taller (#2059).
	const withVideo = bubble.user === videoUser.value
	const width = withVideo ? BUBBLE_WIDTH_VIDEO : BUBBLE_WIDTH
	const left = Math.max(width / 2 + 4, Math.min(gridWidth - width / 2 - 4, centreX))
	const top = Math.min(me.value.y, other.y)
	// Near the top edge the bubble hangs below the chips instead (their legs need ~0.5 tile).
	if (top * t < (withVideo ? 520 : 270)) {
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
		// Chats don't open by walking past: they open when the keys are let go (chatOnStop) or
		// when the other person starts one (onEncounterStarted).
		if (distance > PART_DISTANCE) {
			delete bubbles[other.user]
			dismissed.delete(other.user)
			partFrom(other.user)
		}
	}
	// Someone who left the page also leaves the chat.
	for (const user of new Set([...Object.keys(bubbles), ...encounterByUser.keys()])) {
		if (!others.value.some((o) => o.user === user && !o.offline)) {
			delete bubbles[user]
			partFrom(user)
		}
	}
}

async function openBubble(other, { focus = false, fromPeer = false } = {}) {
	const bubble = reactive({
		pendingText: "",
		focusOnOpen: focus,
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
		bubble.video = data.video || null
		encounterByUser.set(other.user, data.encounter)
		// Met again before the chat burned: it goes on.
		delete notices[data.encounter]
	} catch (e) {
		bubble.error = errorText(e) || __("The chat could not be opened.")
	} finally {
		bubble.loading = false
	}
	if (!bubble.encounter || bubbles[other.user] !== bubble) return
	// Started here with a key: the chat has the keyboard. Started by the other person: only
	// if I'm standing; whoever is walking walks on.
	if (bubble.focusOnOpen || (fromPeer && !held.size)) focusBubble(other.user, bubble.pendingText)
	bubble.pendingText = ""
}

async function focusBubble(user, text = "") {
	await nextTick()
	if (!bubbles[user]?.encounter) return
	bubbleRefs[user]?.focus()
	if (text) bubbleRefs[user]?.insert(text)
}

// The other person started the chat (open_encounter tells this page): open it here too.
function onEncounterStarted(message) {
	const other = others.value.find((o) => o.user === message?.with)
	if (!other || bubbles[other.user] || dismissed.has(other.user)) return
	if (distanceTo(other) > PART_DISTANCE) return
	openBubble(other, { fromPeer: true })
}

// How many movement keys are held (for templates that care whether the user walks).
const heldCount = ref(0)
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

// --- Meeting areas (#2060).

const areas = ref([])
const editingAreas = ref(false)
const areaDraft = ref(null)
const meetingArea = ref(null)
// Left with Esc or "Leave": no rejoining until walking out of that area.
let meetingLeftHere = null

function areaAt(chip) {
	if (!chip) return null
	const cx = chip.x + 0.5
	const cy = chip.y + 0.5
	return areas.value.find((a) => cx >= a.x && cx < a.x + a.width && cy >= a.y && cy < a.y + a.height) || null
}

function joinAreaIfInside() {
	const area = areaAt(me.value)
	if (!area || meetingArea.value?.name === area.name || meetingLeftHere === area.name) return
	meetingArea.value = area
}

function leaveMeetingIfOutside() {
	const here = areaAt(me.value)
	if (meetingLeftHere && here?.name !== meetingLeftHere) meetingLeftHere = null
	if (meetingArea.value && here?.name !== meetingArea.value.name) leaveMeeting(false)
}

function leaveMeeting(byChoice) {
	const left = meetingArea.value
	if (byChoice && left) meetingLeftHere = left.name
	meetingArea.value = null
	// A "Not saved" chat burns once nobody is left in the area (#2062).
	if (left) call(`${API}.leave_area`, { area: left.name }).catch(() => {})
}

// Left column of the meeting view: the area chat fills it down to the mini map.
const areaChatStyle = computed(() => {
	const miniHeight = me.value ? tile.value * me.value.rows : 0
	return {
		left: `${STAGE_PAD}px`,
		top: `${STAGE_PAD}px`,
		width: `${tile.value * (me.value?.cols || 0)}px`,
		bottom: `${miniHeight + STAGE_PAD * 2}px`,
	}
})

// --- People list (#2063) and "chat with" (list or map).

const PEOPLE_KEY = "phamos_ophice_people_open"
const PEOPLE_REFRESH_MS = 15000
const people = ref([])
const hideDetails = ref(false)
const chatWith = ref(null)
const showPeople = ref(readFlag(PEOPLE_KEY, true))
let peopleTimer = null
let peopleSoon = null

function readFlag(key, fallback) {
	try {
		const value = localStorage.getItem(key)
		return value === null ? fallback : value === "1"
	} catch {
		return fallback
	}
}

function togglePeople() {
	showPeople.value = !showPeople.value
	try {
		localStorage.setItem(PEOPLE_KEY, showPeople.value ? "1" : "0")
	} catch {
		// private window: back to the default after a reload
	}
	if (showPeople.value) loadPeople()
}

async function loadPeople() {
	if (!showPeople.value || !me.value) return
	try {
		const data = await call(`${API}.get_people`)
		people.value = data.people || []
		hideDetails.value = Boolean(data.hide_details)
	} catch {
		// the next round tries again
	}
}

/** Someone came, went, moved into an area or set a status: refresh soon, once. */
function peopleChanged() {
	clearTimeout(peopleSoon)
	peopleSoon = setTimeout(loadPeople, 1500)
}

async function setHideDetails(hide) {
	hideDetails.value = hide
	try {
		await call(`${API}.set_hide_details`, { hide: hide ? 1 : 0 })
	} catch (e) {
		hideDetails.value = !hide
		toast.error(errorText(e) || __("The setting could not be saved."))
	}
	loadPeople()
}

function openChatWith(person, event) {
	if (!person?.user || person.user === me.value?.user) return
	chatWith.value = { person, at: { x: event?.clientX ?? 200, y: event?.clientY ?? 200 } }
}

function nameOf(user) {
	if (user === me.value?.user) return me.value.full_name
	return others.value.find((o) => o.user === user)?.full_name || user
}

function setAreas(list) {
	areas.value = list || []
	// The area I am meeting in was changed or deleted by someone.
	if (meetingArea.value) {
		const same = areas.value.find((a) => a.name === meetingArea.value.name)
		if (!same || same.jitsi_room !== meetingArea.value.jitsi_room || same.jitsi_domain !== meetingArea.value.jitsi_domain) {
			meetingArea.value = null
		} else meetingArea.value = same
	}
}

async function saveArea(values) {
	try {
		await call(`${API}.save_area`, {
			name: values.name || null,
			title: values.title,
			meeting_url: values.meeting_url,
			x: values.x,
			y: values.y,
			width: values.width,
			height: values.height,
			chat_mode: values.chat_mode || "Saved",
		})
	} catch (e) {
		throw new Error(errorText(e) || __("The area could not be saved."))
	}
}

async function deleteArea(area) {
	try {
		await call(`${API}.delete_area`, { name: area.name })
	} catch (e) {
		throw new Error(errorText(e) || __("The area could not be deleted."))
	}
}

// --- Burn notices (#2057).

const notices = reactive({})
const noticeList = computed(() => Object.values(notices))
const now = ref(Date.now())
let nowTimer = null

// --- Status (#2053): be right back / away with a note and a return time.

const AWAY_GRACE_MS = 3600 * 1000
const statusOpen = ref(false)
// For "back in 20 minutes": a slow clock is enough.
const clock = ref(Date.now())
const clockTimer = setInterval(() => (clock.value = Date.now()), 30000)
let statusClearing = false

const statusChips = computed(() => {
	if (!me.value) return []
	return [me.value, ...others.value].filter((chip) => chip.status)
})

function tagStyle(chip) {
	// Above the chip, clear of its ring; towards the map's edges the tag shifts inwards (the tail
	// keeps pointing at the chip), so it is never cut off.
	const share = Math.round(10 + (80 * chip.x) / Math.max(1, me.value.cols - 1))
	return {
		left: "0px",
		top: "0px",
		"--tail": `${share}%`,
		transform: `translate(${(chip.x + 0.5) * tile.value}px, ${(chip.y - 0.12) * tile.value}px) translate(-${share}%, -100%)`,
	}
}

async function saveStatus(values) {
	try {
		me.value.status = await call(`${API}.set_status`, values)
	} catch (e) {
		throw new Error(errorText(e) || __("The status could not be set."))
	}
}

/** Moving means I'm back: the status goes. */
function backFromStatus() {
	if (!me.value?.status || statusClearing) return
	statusClearing = true
	me.value.status = null
	call(`${API}.set_status`, { kind: "" })
		.catch(() => {})
		.finally(() => (statusClearing = false))
}

function onRemoteStatus(message) {
	if (!message?.user) return
	if (message.user === me.value?.user) {
		// Set in another tab of mine.
		me.value.status = message.status || null
		return
	}
	const other = others.value.find((o) => o.user === message.user)
	if (!other) return
	other.status = message.status || null
	if (other.offline && !other.status) others.value = others.value.filter((o) => o !== other)
}

function partFrom(user) {
	const encounter = encounterByUser.get(user)
	if (!encounter) return
	encounterByUser.delete(user)
	call(`${API}.part_encounter`, { encounter })
		.then((notice) => notice && upsertNotice(notice))
		.catch(() => {})
}

function upsertNotice(notice) {
	if (!notice?.encounter) return
	const existing = notices[notice.encounter]
	if (existing?.state) return // already saved or burned
	const fields = {
		encounter: notice.encounter,
		with: notice.with,
		full_name: notice.full_name,
		user_image: notice.user_image,
		deadline: Date.now() + notice.burn_in * 1000,
		total: 60,
		saved_by_me: notice.saved_by_me,
		saved_by_peer: notice.saved_by_peer,
	}
	if (existing) Object.assign(existing, fields)
	else notices[notice.encounter] = reactive({ ...fields, state: "", saving: false, burnAsked: false })
	startClock()
}

function finishNotice(encounter, state) {
	const notice = notices[encounter]
	for (const [user, open] of encounterByUser) if (open === encounter) encounterByUser.delete(user)
	for (const bubble of Object.values(bubbles)) if (bubble.encounter === encounter) delete bubbles[bubble.user]
	if (!notice) return
	notice.state = state
	setTimeout(() => delete notices[encounter], state === "saved" ? 5000 : 4000)
}

async function saveEncounter(notice) {
	notice.saving = true
	try {
		const result = await call(`${API}.save_encounter`, { encounter: notice.encounter })
		notice.saved_by_me = true
		if (result?.saved) finishNotice(notice.encounter, "saved")
	} catch (e) {
		toast.error(errorText(e) || __("The chat could not be saved."))
	} finally {
		notice.saving = false
	}
}

// The countdown: at zero the page asks the server to burn (the scheduler does it for closed tabs).
function startClock() {
	if (nowTimer) return
	nowTimer = setInterval(() => {
		now.value = Date.now()
		for (const notice of Object.values(notices)) {
			if (!notice.state && !notice.burnAsked && notice.deadline <= now.value) {
				notice.burnAsked = true
				call(`${API}.burn_if_due`, { encounter: notice.encounter })
					.then((r) => r?.burned && finishNotice(notice.encounter, "burned"))
					.catch(() => {})
			}
		}
		if (!Object.keys(notices).length) {
			clearInterval(nowTimer)
	clearInterval(clockTimer)
	clearInterval(peopleTimer)
	clearTimeout(peopleSoon)
			nowTimer = null
		}
	}, 250)
}

const NOTICE_EVENTS = [
	["ophice_burn_notice", upsertNotice],
	["ophice_save_vote", upsertNotice],
	["ophice_burn_cancel", (m) => delete notices[m?.encounter]],
	["ophice_saved", (m) => finishNotice(m?.encounter, "saved")],
	["ophice_burned", (m) => finishNotice(m?.encounter, "burned")],
]

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
	["ophice_presence", upsertOther],
	["ophice_move", onRemoteMove],
	["ophice_leave", onRemoteLeave],
	["ophice_message", onEncounterMessage],
	["ophice_encounter_started", onEncounterStarted],
	["ophice_areas", (message) => setAreas(message?.areas)],
	["ophice_status", (message) => (onRemoteStatus(message), peopleChanged())],
	["ophice_leave", peopleChanged],
	["ophice_encounter_started", peopleChanged],
	[
		"ophice_background",
		(message) => {
			background.value = message?.url || ""
			// Not while I'm dragging the sliders myself (my own echo would jump back).
			if (!layoutTimer) backgroundLayout.value = message?.layout || { ...FITTED }
			if (!background.value) adjustingBackground.value = false
		},
	],
	...NOTICE_EVENTS,
	// Rejoin after a lost connection: the others may have moved meanwhile.
	["connect", () => (heartbeat(), refreshOthers())],
]

function blocked(x, y) {
	// In the air nothing blocks: that is the point of jumping.
	if (jump || flying.value) return false
	return others.value.some((o) => !o.offline && Math.hypot(o.x - x, o.y - y) < MIN_DISTANCE)
}

// --- Jump (Space): a short hop forward that passes over other chips.

const JUMP_MS = 420
const JUMP_DISTANCE = 2 // tiles, in the direction walked (or last walked)
const jumping = ref(false)
const doubleJumped = ref(false)
// Space still held when the jump lands: hovering with wings, over everyone, until it's let go.
const flying = ref(false)
let spaceHeld = false
let jump = null // { dir: [x, y], left: tiles still to cover, doubled }
let lastDir = [1, 0]

function startJump() {
	if (jump || !me.value) return
	jump = { dir: lastDir, left: JUMP_DISTANCE, doubled: false }
	jumping.value = true
	doubleJumped.value = false
	if (!frame) {
		lastTime = performance.now()
		frame = requestAnimationFrame(tick)
	}
}

/** Space again in the air: a second hop, as far again, from where the chip is now. */
function doubleJump() {
	jump.left += JUMP_DISTANCE
	jump.doubled = true
	doubleJumped.value = true
}

/** Back on the ground: slide on until no chip is underneath, then as after a walk. */
function land(dir = lastDir) {
	flying.value = false
	// Landed on someone: a little further along, up to 3 tiles.
	for (let extra = 0; extra <= 3 && blocked(me.value.x, me.value.y); extra += 0.1) {
		moveTo(me.value.x + dir[0] * 0.1, me.value.y + dir[1] * 0.1)
	}
	scheduleSave()
	queueMove()
	checkEncounters()
	leaveMeetingIfOutside()
	if (!held.size) chatOnStop()
}

/** The jump's share of this frame's movement; then hover (Space held) or land. */
function jumpStep(dt) {
	const step = Math.min(jump.left, (JUMP_DISTANCE * dt * 1000) / JUMP_MS)
	jump.left -= step
	const [dx, dy] = jump.dir
	moveTo(me.value.x + dx * step, me.value.y + dy * step)
	if (jump.left > 1e-6) return
	const dir = jump.dir
	jump = null
	jumping.value = false
	doubleJumped.value = false
	if (spaceHeld) flying.value = true
	else land(dir)
}

function moveTo(x, y) {
	me.value.x = Math.max(0, Math.min(me.value.cols - 1, x))
	me.value.y = Math.max(0, Math.min(me.value.rows - 1, y))
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
	if ((!keys.size && !jump) || !me.value) {
		frame = null
		moving.value = false
		if (sendTimer) sendMove()
		return
	}
	const length = Math.hypot(dx, dy)
	if (length) lastDir = [dx / length, dy / length]
	if (jump) {
		moving.value = true
		jumpStep(dt)
		scheduleSave()
		queueMove()
		checkEncounters()
		leaveMeetingIfOutside()
	}
	if (length && !jump) {
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
		leaveMeetingIfOutside()
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
		background.value = data.background || ""
		backgroundLayout.value = data.background_layout || { ...FITTED }
		setAreas(data.areas)
		for (const notice of data.notices || []) upsertNotice(notice)
		for (const chip of data.others || []) upsertOther(chip)
	} catch (e) {
		error.value = __("Ophice could not be loaded.")
		return
	}
	checkEncounters()
	for (const [event, handler] of SOCKET_EVENTS) socket?.on?.(event, handler)
	heartbeat()
	heartbeatTimer = setInterval(heartbeat, HEARTBEAT_MS)
	loadPeople()
	peopleTimer = setInterval(loadPeople, PEOPLE_REFRESH_MS)
})

onBeforeUnmount(() => {
	window.removeEventListener("keydown", onKeydown)
	window.removeEventListener("keyup", onKeyup)
	window.removeEventListener("blur", releaseAll)
	window.removeEventListener("pagehide", leaveOnPagehide)
	for (const [event, handler] of SOCKET_EVENTS) socket?.off?.(event, handler)
	clearInterval(heartbeatTimer)
	clearInterval(nowTimer)
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
.ophice-grid {
	background-image: linear-gradient(to right, var(--outline-gray-2) 1px, transparent 1px),
		linear-gradient(to bottom, var(--outline-gray-2) 1px, transparent 1px);
	background-size: var(--tile) var(--tile);
}
/* An uploaded image fills the grid; the lines stay on top of it. */
.ophice-grid--image {
	background-image: linear-gradient(to right, var(--outline-gray-2) 1px, transparent 1px),
		linear-gradient(to bottom, var(--outline-gray-2) 1px, transparent 1px), var(--background-image);
	background-size: var(--tile) var(--tile), var(--tile) var(--tile), var(--background-size, cover);
	background-position: 0 0, 0 0, var(--background-position, center);
	background-repeat: repeat, repeat, no-repeat;
}
.ophice-chip {
	top: 0;
	left: 0;
	will-change: transform;
}
/* Perimeters: a circle per chip, stronger for my own, green when touching another. A light edge
   with a thin dark outline keeps it visible on any background image, light or dark. */
.ophice-perimeter {
	top: 0;
	left: 0;
	border: 2px dashed rgba(255, 255, 255, 0.85);
	box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.35), inset 0 0 0 1px rgba(0, 0, 0, 0.35);
	background: rgba(255, 255, 255, 0.14);
	transition: background-color 150ms, border-color 150ms;
	will-change: transform;
}
.ophice-perimeter--me {
	border-color: rgba(96, 165, 250, 0.95);
	background: rgba(59, 130, 246, 0.18);
}
.ophice-perimeter--contact {
	border-style: solid;
	border-color: rgba(74, 222, 128, 0.95);
	background: rgba(34, 197, 94, 0.24);
}
/* Other chips arrive about 8 times a second: glide between the updates. */
.ophice-chip--remote {
	transition: transform 130ms linear;
}
@media (prefers-reduced-motion: reduce) {
	.ophice-chip--remote {
		transition: none;
	}
}
</style>
