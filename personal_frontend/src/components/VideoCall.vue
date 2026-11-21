<template>
	<!-- The video call of an encounter (#2059): Jitsi, joined muted with the camera off. -->
	<div class="relative aspect-video w-full overflow-hidden bg-surface-gray-7" data-testid="video-call">
		<div ref="host" class="h-full w-full" />
		<!-- Never in Jitsi's way: no clicks, at the bottom edge, and gone after a while. -->
		<p
			v-if="state === 'failed' || (state === 'joining' && !quiet)"
			class="pointer-events-none absolute inset-x-0 bottom-0 bg-black/50 px-2 py-1 text-center text-xs text-white"
		>
			{{ state === "failed" ? __("The video call could not be started.") : __("Joining the call…") }}
		</p>
	</div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from "vue"
import { __ } from "@spa/utils/i18n.js"

const props = defineProps({
	/** Jitsi host, for example meet.jit.si */
	domain: { type: String, required: true },
	room: { type: String, required: true },
	displayName: { type: String, default: "" },
})
const emit = defineEmits(["joined"])

const host = ref(null)
const state = ref("joining")
// Jitsi shows its own progress; our label only bridges the first seconds.
const quiet = ref(false)
const quietTimer = setTimeout(() => (quiet.value = true), 8000)
let api = null
let disposed = false

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
		},
		interfaceConfigOverwrite: { MOBILE_APP_PROMO: false, SHOW_JITSI_WATERMARK: false },
	})
	api.addListener("videoConferenceJoined", () => {
		state.value = "joined"
		emit("joined")
	})
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
}

// Walking away or Esc unmounts the bubble: leave the call.
onBeforeUnmount(() => {
	clearTimeout(quietTimer)
	dispose()
})
</script>
