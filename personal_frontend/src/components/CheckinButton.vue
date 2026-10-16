<!-- Check-in status in the top bar (#1571): "in since 08:02" and, right after a check-in or out,
     the undo ring. Checking in and out itself is in the Create menu. -->
<template>
	<div v-if="usable" class="flex items-center gap-2">
		<span
			class="hidden items-center gap-1 text-xs md:flex"
			:class="state.stale_in ? 'text-ink-amber-4' : 'text-ink-gray-5'"
			aria-live="polite"
		>
			<FeatherIcon v-if="state.stale_in" name="alert-triangle" class="h-3.5 w-3.5" />
			{{ captionText }}
		</span>
		<UndoRing
			v-if="checkin.pending"
			:key="checkin.pending.name"
			:seconds="state.undo_seconds || 10"
			:label="undoLabel"
			role="status"
			@undo="revoke"
			@expired="checkin.pending = null"
		/>
	</div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted } from "vue"
import { call } from "frappe-ui"
import { caption, isUndoKey } from "@spa/utils/checkinSummary.js"
import { formatTime as formatTimeFull, parseSystemDatetimeToUserDate } from "@spa/utils/datetime.js"
import { notify } from "@spa/utils/notify.js"
import spaConfig from "@/config"
import { checkin, checkinUsable, loadCheckin, setCheckin } from "@/checkinStore.js"
import UndoRing from "./UndoRing.vue"

// Hours and minutes only; the system time format may include seconds.
const formatTime = (value) => formatTimeFull(value).slice(0, 5)
const API = spaConfig.api

const state = computed(() => checkin.state)
const usable = computed(() => checkinUsable(state.value))
const captionText = computed(() => caption(state.value, formatTime, formatDay))
const undoLabel = computed(() => {
	const pending = checkin.pending
	if (!pending) return "Undo"
	const what = pending.log_type === "IN" ? "check-in" : "check-out"
	return `Revoke the ${what} at ${formatTime(pending.time)} (Ctrl+Z)`
})

function formatDay(value) {
	const date = parseSystemDatetimeToUserDate(String(value))
	return date ? date.toLocaleDateString([], { weekday: "short" }) : ""
}

function errorText(e, fallback) {
	return e?.messages?.[0] || e?.message || fallback
}

async function revoke() {
	const pending = checkin.pending
	if (!pending) return
	checkin.pending = null
	try {
		setCheckin(await call(`${API}.revoke_checkin`, { name: pending.name }))
		notify.success(pending.log_type === "IN" ? "Check-in revoked" : "Check-out revoked")
	} catch (e) {
		notify.error(errorText(e, "Could not revoke it"))
		loadCheckin()
	}
}

function onKeydown(event) {
	if (checkin.pending && isUndoKey(event)) {
		event.preventDefault()
		revoke()
	}
}

onMounted(() => window.addEventListener("keydown", onKeydown))
onBeforeUnmount(() => window.removeEventListener("keydown", onKeydown))
</script>
