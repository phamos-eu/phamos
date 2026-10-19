<template>
	<div class="h-full min-h-0 overflow-y-auto bg-surface-gray-1 p-5">
		<div class="mx-auto flex max-w-3xl flex-col gap-4">
			<div v-if="error" class="rounded-lg border border-outline-gray-2 bg-surface-red-1 p-4 text-sm text-ink-red-4">{{ error }}</div>
			<p v-else-if="loaded && !groups.length" class="text-sm text-ink-gray-5">{{ __("No check-ins yet.") }}</p>
			<section
				v-for="group in groups"
				:key="group.date"
				class="rounded-lg border border-outline-gray-2 bg-surface-white"
			>
				<header class="flex items-center justify-between border-b border-outline-gray-1 px-4 py-2 text-sm">
					<span class="font-medium text-ink-gray-9">{{ group.label }}</span>
					<span class="text-ink-gray-5">
						<span v-if="group.missingOut" class="mr-2 text-ink-amber-4">{{ __("no check-out") }}</span>{{ formatWorked(group.minutes) }}
					</span>
				</header>
				<ul class="divide-y divide-outline-gray-1">
					<li v-for="log in group.logs" :key="log.name" class="flex items-center gap-3 px-4 py-2 text-sm">
						<span class="w-12 tabular-nums text-ink-gray-9">{{ shortTime(log.time) }}</span>
						<span
							class="rounded px-1.5 py-0.5 text-xs"
							:class="log.log_type === 'IN' ? 'bg-surface-green-2 text-ink-green-3' : 'bg-surface-gray-2 text-ink-gray-6'"
						>
							{{ log.log_type === "IN" ? __("In") : __("Out") }}
						</span>
						<span class="min-w-0 flex-1 truncate text-xs text-ink-gray-5">{{ log.device_id || "" }}</span>
						<span v-if="log.attendance" class="text-xs text-ink-gray-5" :title="__('Counted for attendance')">✓ {{ __("attendance") }}</span>
						<button type="button" class="text-xs text-ink-gray-5 hover:underline" @click="openDesk(deskRecordUrl('Employee Checkin', log.name))">
							{{ __("Desk") }} ↗
						</button>
					</li>
				</ul>
			</section>
			<Button v-if="hasMore" class="self-center" :loading="loading" @click="load(false)">{{ __("Load older check-ins") }}</Button>
		</div>
	</div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue"
import { call } from "frappe-ui"
import { useUserRealtime } from "@spa/composables/useUserRealtime.js"
import { openDesk } from "@spa/utils/appWindow.js"
import { formatWorked, worked } from "@spa/utils/checkinSummary.js"
import { formatDate, formatTime, todayIsoInUserTz, weekdayName } from "@spa/utils/datetime.js"
import { __ } from "@spa/utils/i18n.js"
import { deskRecordUrl } from "@spa/utils/deskUrl.js"
import spaConfig from "@/config"

const PAGE = 100
const logs = ref([])
const hasMore = ref(false)
const loading = ref(false)
const loaded = ref(false)
const error = ref("")

const shortTime = (value) => formatTime(value).slice(0, 5)
const groups = computed(() => {
	const byDay = new Map()
	for (const log of logs.value) {
		const day = String(log.time).slice(0, 10)
		if (!byDay.has(day)) byDay.set(day, [])
		byDay.get(day).push(log)
	}
	const today = todayIsoInUserTz()
	return [...byDay.entries()].map(([day, dayLogs]) => {
		const chronological = [...dayLogs].reverse()
		const d = new Date(`${day}T12:00:00`)
		return {
			date: day,
			label: `${weekdayName(d)} ${formatDate(day)}`,
			logs: dayLogs,
			minutes: worked(chronological, day === today ? new Date() : null),
			missingOut: chronological[chronological.length - 1].log_type === "IN" && day !== today,
		}
	})
})

async function load(reset = true) {
	loading.value = true
	try {
		const page = await call(`${spaConfig.api}.get_my_checkins`, { start: reset ? 0 : logs.value.length, page_length: PAGE })
		logs.value = reset ? page.logs : [...logs.value, ...page.logs]
		hasMore.value = page.has_more
		error.value = ""
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || __("Could not load your check-ins")
	} finally {
		loading.value = false
		loaded.value = true
	}
}

useUserRealtime("cockpit_checkin_changed", () => load(true))
onMounted(() => load(true))
</script>
