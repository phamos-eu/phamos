<template>
	<!-- The video call of an encounter (#2059): Jitsi, joined muted with the camera off. -->
	<div
		class="relative aspect-video w-full overflow-hidden bg-surface-gray-7"
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
		<!-- Browsers play the other person's audio only after a click inside the Jitsi frame
		     (autoplay rule; keys pressed in Ophice don't count for that frame). -->
		<!-- Clicks pass through to the video below, which is exactly the click the browser wants. -->
		<p
			v-if="ready && !frameClicked"
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
		</div>
	</div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from "vue"
import { FeatherIcon } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"

const props = defineProps({
	/** Jitsi host, for example meet.jit.si */
	domain: { type: String, required: true },
	room: { type: String, required: true },
	displayName: { type: String, default: "" },
})
const emit = defineEmits(["joined", "toggled", "stolen"])

const host = ref(null)
const state = ref("joining")
// Jitsi shows its own progress; our label only bridges the first seconds.
const quiet = ref(false)
const quietTimer = setTimeout(() => (quiet.value = true), 8000)
let api = null
let disposed = false
// Mic and camera start off (decision of 2026-11-21); Jitsi reports every change.
const ready = ref(false)
// A click into Jitsi's frame moves the focus there: the page's window loses it (blur). Without
// the pointer over the video it was Jitsi itself (it focuses on load): that is not a click,
// and the keyboard goes back to Ophice ("stolen").
const frameClicked = ref(false)
const pointerOver = ref(false)
function onWindowBlur() {
	setTimeout(() => {
		if (!host.value || !host.value.contains(document.activeElement)) return
		if (pointerOver.value) frameClicked.value = true
		else emit("stolen")
	})
}
const audioMuted = ref(true)
const videoMuted = ref(true)

function toggle(command) {
	api?.executeCommand(command)
	// The chat keeps the keyboard after a click on a switch.
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
			startWithAudioMuted: true,
			startWithVideoMuted: true,
			prejoinPageEnabled: false,
			prejoinConfig: { enabled: false },
			disableDeepLinking: true,
			toolbarButtons: ["microphone", "camera", "tileview", "hangup"],
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
	})
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

// Walking away or Esc unmounts the bubble: leave the call.
onBeforeUnmount(() => {
	window.removeEventListener("blur", onWindowBlur)
	clearTimeout(quietTimer)
	dispose()
})
</script>
