<template>
	<div v-if="visible" class="mb-2 border-b border-outline-gray-2 pb-2">
		<div
			v-if="collapsed"
			class="flex justify-center py-1"
			:title="summary"
			role="status"
			:aria-label="summary"
		>
			<span class="h-2.5 w-2.5 rounded-full" :class="checkedIn ? 'bg-surface-green-3' : 'bg-surface-gray-4'" />
		</div>
		<div v-else class="px-2" role="status" aria-live="polite">
			<div class="mb-1 flex items-center justify-between text-xs font-medium text-ink-gray-7">
				<span>Today</span>
				<span>{{ formatWorked(minutes) }}</span>
			</div>
			<ul v-if="rows.length" class="max-h-32 space-y-0.5 overflow-y-auto">
				<li v-for="row in rows" :key="row.name" class="flex items-center gap-2 text-xs text-ink-gray-6">
					<span class="w-10 tabular-nums text-ink-gray-8">{{ formatTime(row.time) }}</span>
					<span>{{ row.log_type === "IN" ? "in" : "out" }}</span>
					<span v-if="row.running" class="h-1.5 w-1.5 rounded-full bg-surface-green-3" title="Checked in" />
				</li>
			</ul>
			<p v-else class="text-xs text-ink-gray-5">No check-ins yet today.</p>
			<button
				type="button"
				class="mt-1 text-xs text-ink-gray-5 hover:text-ink-gray-8 hover:underline"
				@click="openDesk(deskUrl)"
			>
				All check-ins ↗
			</button>
		</div>
	</div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue"
import { formatWorked, liveWorkedMinutes, todayRows } from "@spa/utils/checkinSummary.js"
import { formatTime as formatTimeFull } from "@spa/utils/datetime.js"
import { openDesk } from "@spa/utils/appWindow.js"
import { checkin } from "@/checkinStore.js"

defineProps({ collapsed: { type: Boolean, default: false } })

// Hours and minutes only; the system time format may include seconds.
const formatTime = (value) => formatTimeFull(value).slice(0, 5)
const tick = ref(Date.now())
let timer = null

const state = computed(() => checkin.state)
const visible = computed(() => Boolean(state.value?.available && state.value.employee))
const checkedIn = computed(() => state.value?.next_action === "OUT" && !state.value.stale_in)
const rows = computed(() => todayRows(state.value))
const minutes = computed(() => liveWorkedMinutes(state.value, (tick.value - checkin.loadedAt) / 1000))
const summary = computed(() => {
	const since = state.value?.last ? ` since ${formatTime(state.value.last.time)}` : ""
	return `${checkedIn.value ? "Checked in" : "Checked out"}${since} · ${formatWorked(minutes.value)} today`
})
const deskUrl = computed(
	() => `/app/employee-checkin?employee=${encodeURIComponent(state.value?.employee || "")}`
)

onMounted(() => (timer = setInterval(() => (tick.value = Date.now()), 30000)))
onBeforeUnmount(() => clearInterval(timer))
</script>
