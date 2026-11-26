<template>
	<!-- A Jitsi video call: encounter (#2059), meeting area (#2060), guests. Joined with mic and camera on
	     (#2108); the person being approached with both off until their first click (#2165). -->
	<div
		class="relative w-full overflow-hidden bg-surface-gray-7"
		:class="{ 'aspect-video': !fill }"
		data-testid="video-call"
		@mouseenter="pointerOver = true"
		@mouseleave="pointerOver = false"
	>
		<div ref="host" class="h-full w-full" />
		<!-- Never in Jitsi's way: no clicks, at the bottom edge, and gone after a while. -->
		<p
			v-if="state === 'failed' || (state === 'joining' && !quiet)"
			class="pointer-events-none absolute inset-x-0 bottom-0 bg-black/50 px-2 py-1 text-center text-xs text-white"
		>
			{{ state === "failed" ? __("The video call could not be started.") : __("Joining the call…") }}
		</p>
		<!-- Approached (#2165): mic and camera wait for the first click on the call. -->
		<p
			v-if="ready && waiting"
			class="pointer-events-none absolute inset-x-2 bottom-2 flex items-center justify-center gap-1.5 rounded-md bg-black/70 px-2 py-1 text-xs text-white"
			data-testid="start-off-hint"
		>
			<FeatherIcon name="video-off" class="h-3.5 w-3.5" />
			{{ __("Your mic and camera are off. Click to turn them on.") }}
		</p>
		<!-- Browsers play the other person's audio only after a click inside the Jitsi frame
		     (autoplay rule; keys pressed in Ophice don't count for that frame). -->
		<!-- Clicks pass through to the video below, which is exactly the click the browser wants. -->
		<p
			v-else-if="ready && !frameClicked"
			class="pointer-events-none absolute inset-x-2 bottom-2 flex items-center justify-center gap-1.5 rounded-md bg-black/70 px-2 py-1 text-xs text-white"
			data-testid="sound-hint"
		>
			<FeatherIcon name="volume-2" class="h-3.5 w-3.5" />
			{{ __("No sound? Click once into the video.") }}
		</p>
		<!-- Our own switches: Jitsi hides its toolbar in a frame this small. They drive Jitsi
		     through its API and show the state Jitsi reports. -->
		<div v-if="ready" class="absolute left-2 top-2 flex gap-1.5" data-testid="call-controls">
			<button
				type="button"
				class="flex h-8 w-8 items-center justify-center rounded-full text-white shadow focus:outline-none focus-visible:ring-2 focus-visible:ring-white"
				:class="audioMuted ? 'bg-red-600 hover:bg-red-500' : 'bg-black/60 hover:bg-black/80'"
				:title="audioMuted ? __('Turn on the microphone') : __('Turn off the microphone')"
				:aria-pressed="!audioMuted"
				data-testid="toggle-mic"
				@click="toggle('toggleAudio')"
			>
				<FeatherIcon :name="audioMuted ? 'mic-off' : 'mic'" class="h-4 w-4" />
			</button>
			<button
				type="button"
				class="flex h-8 w-8 items-center justify-center rounded-full text-white shadow focus:outline-none focus-visible:ring-2 focus-visible:ring-white"
				:class="videoMuted ? 'bg-red-600 hover:bg-red-500' : 'bg-black/60 hover:bg-black/80'"
				:title="videoMuted ? __('Turn on the camera') : __('Turn off the camera')"
				:aria-pressed="!videoMuted"
				data-testid="toggle-camera"
				@click="toggle('toggleVideo')"
			>
				<FeatherIcon :name="videoMuted ? 'video-off' : 'video'" class="h-4 w-4" />
			</button>
			<!-- Video quality: starts at the lowest level with video; a click steps up, after "HD" back down. -->
			<button
				type="button"
				class="flex h-8 min-w-8 items-center justify-center rounded-full bg-black/60 px-2 text-[11px] font-semibold text-white shadow hover:bg-black/80 focus:outline-none focus-visible:ring-2 focus-visible:ring-white"
				:title="qualityTitle"
				:aria-label="qualityTitle"
				data-testid="video-quality"
				@click="nextQuality"
			>
				{{ currentQuality.short }}
			</button>
		</div>
	</div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue"
import { FeatherIcon } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"
import {
	JITSI_TOOLBAR_BUTTONS,
	QUALITY_LEVELS,
	callActivation,
	jitsiStartConfig,
	nextQualityLevel,
	qualityLevel,
	qualitySync,
} from "../utils/ophiceCall.js"

const props = defineProps({
	/** Jitsi host, for example meet.jit.si */
	domain: { type: String, required: true },
	room: { type: String, required: true },
	displayName: { type: String, default: "" },
	/** Fill the parent's height instead of keeping 16:9 (meeting view, #2061). */
	fill: { type: Boolean, default: false },
	/** Join with mic and camera off, no device touched, until the first click (approached, #2165). Read once. */
	startOff: { type: Boolean, default: false },
})
const emit = defineEmits(["joined", "toggled", "stolen", "activated"])

const host = ref(null)
const state = ref("joining")
// Jitsi shows its own progress; our label only bridges the first seconds.
const quiet = ref(false)
const quietTimer = setTimeout(() => (quiet.value = true), 8000)
let api = null
let disposed = false
// Mic and camera start on: whoever joins a call wants to talk (#2108, replaces the start-off
// decision of 2026-11-21). The browser still asks once for the permission. Jitsi reports every change.
// Not for the person being approached (#2165): off until they click the call.
const ready = ref(false)
const waiting = ref(props.startOff)
const activation = callActivation({
	isAudioMuted: () => api?.isAudioMuted() ?? Promise.resolve(false),
	isVideoMuted: () => api?.isVideoMuted() ?? Promise.resolve(false),
	run: (command) => api?.executeCommand(command),
})
/**
 * The first click on the call (anywhere on the bubble, or into the video): mic and camera on.
 * @param {number} delay  ms to wait first: a click into the video may be on Jitsi's own mic or
 *   camera button; once Jitsi switched that one on, only the other one is still off.
 */
function activate(delay = 0) {
	if (!waiting.value) return
	waiting.value = false
	emit("activated")
	setTimeout(() => activation.click(), delay)
}
// A click into Jitsi's frame moves the focus there: the page's window loses it (blur). Without
// the pointer over the video it was Jitsi itself (it focuses on load): that is not a click,
// and the keyboard goes back to Ophice ("stolen").
const frameClicked = ref(false)
const pointerOver = ref(false)
const FRAME_CLICK_DELAY = 800
function onWindowBlur() {
	setTimeout(() => {
		if (!host.value || !host.value.contains(document.activeElement)) return
		if (pointerOver.value) {
			frameClicked.value = true
			// The focus moves on the press; Jitsi's button acts on the release.
			activate(FRAME_CLICK_DELAY)
		} else emit("stolen")
	})
}
const audioMuted = ref(props.startOff)
const videoMuted = ref(props.startOff)

function toggle(command) {
	// The first click turns both on (#2165); toggling as well would switch this one off again.
	if (waiting.value) activate()
	else api?.executeCommand(command)
	// The chat keeps the keyboard after a click on a switch.
	emit("toggled")
}

// Video quality: starts at 180p, the lowest level with a picture (PM, 2026-11-25); who needs
// more steps it up. Jitsi's own values count once ours is confirmed (qualitySync).
const QUALITY_INFO = {
	180: { short: "LD", label: `${__("Low")} (180p)` },
	360: { short: "SD", label: `${__("Standard")} (360p)` },
	720: { short: "HD", label: `${__("High")} (720p)` },
}
const quality = ref(QUALITY_LEVELS[0])
const currentQuality = computed(() => QUALITY_INFO[qualityLevel(quality.value)])
const qualityTitle = computed(() =>
	__("Video quality: {0}. Click for {1}.", [currentQuality.value.label, QUALITY_INFO[nextQualityLevel(quality.value)].label])
)
const qualityState = qualitySync(
	(height) => api?.executeCommand("setVideoQuality", height),
	(height) => (quality.value = height)
)
function nextQuality() {
	qualityState.choose(nextQualityLevel(quality.value))
	emit("toggled")
}

// external_api.js once per page and domain.
const scripts = (window.__phamosJitsiScripts ||= {})
function loadJitsi(domain) {
	if (window.JitsiMeetExternalAPI) return Promise.resolve()
	scripts[domain] ||= new Promise((resolve, reject) => {
		const script = document.createElement("script")
		script.src = `https://${domain}/external_api.js`
		script.async = true
		script.onload = resolve
		script.onerror = () => {
			delete scripts[domain]
			reject(new Error("Jitsi could not be loaded"))
		}
		document.head.appendChild(script)
	})
	return scripts[domain]
}

onMounted(async () => {
	try {
		await loadJitsi(props.domain)
	} catch {
		state.value = "failed"
		return
	}
	if (disposed || !host.value) return
	api = new window.JitsiMeetExternalAPI(props.domain, {
		roomName: props.room,
		parentNode: host.value,
		width: "100%",
		height: "100%",
		userInfo: { displayName: props.displayName },
		configOverwrite: {
			...jitsiStartConfig({ startOff: props.startOff }),
			disableDeepLinking: true,
			toolbarButtons: JITSI_TOOLBAR_BUTTONS,
			toolbarConfig: { alwaysVisible: true },
		},
		interfaceConfigOverwrite: { MOBILE_APP_PROMO: false, SHOW_JITSI_WATERMARK: false },
	})
	ready.value = true
	window.addEventListener("blur", onWindowBlur)
	api.addListener("videoConferenceJoined", () => {
		state.value = "joined"
		emit("joined")
		// The real state, should Jitsi have ignored the start settings.
		api?.isAudioMuted().then((muted) => (audioMuted.value = muted))
		api?.isVideoMuted().then((muted) => (videoMuted.value = muted))
		qualityState.start()
		// Started off and already clicked: mic and camera on now (#2165).
		if (props.startOff) activation.joined()
	})
	api.addListener("videoQualityChanged", ({ videoQuality }) => qualityState.reported(videoQuality))
	api.addListener("audioMuteStatusChanged", ({ muted }) => (audioMuted.value = muted))
	api.addListener("videoMuteStatusChanged", ({ muted }) => (videoMuted.value = muted))
	// Hanging up inside Jitsi just leaves; the chat stays.
	api.addListener("readyToClose", () => dispose())
})

function dispose() {
	disposed = true
	try {
		api?.dispose()
	} catch {
		// already gone
	}
	api = null
	ready.value = false
}

defineExpose({ activate })

// Walking away or Esc unmounts the bubble: leave the call.
onBeforeUnmount(() => {
	window.removeEventListener("blur", onWindowBlur)
	clearTimeout(quietTimer)
	qualityState.stop()
	dispose()
})
</script>
