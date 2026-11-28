<template>
	<!-- Who is there and on what they work, live (#1978). Full height; only the list scrolls. -->
	<div class="flex h-full min-h-0 flex-col gap-3 bg-surface-gray-1 p-4">
		<div class="flex flex-wrap items-center justify-between gap-2">
			<p class="text-sm text-ink-gray-6">
				{{ __("{0} of {1} checked in · updated {2}", [checkedIn, members.length, updatedLabel]) }}
			</p>
			<IssueChatButton v-if="team" doctype="Team" :record-name="team" :subject="team" :api="spaConfig.api" />
		</div>

		<div v-if="error" class="rounded-lg border border-outline-gray-2 bg-surface-red-1 p-4 text-sm text-ink-red-4">
			{{ error }}
		</div>
		<div v-else-if="loading" class="flex flex-1 items-center justify-center text-sm text-ink-gray-5">
			{{ __("Loading team mates…") }}
		</div>
		<section v-else class="min-h-0 flex-1 overflow-auto rounded-lg border border-outline-gray-2 bg-surface-white">
			<ul>
				<li v-if="!members.length" class="px-4 py-3 text-sm text-ink-gray-5">{{ __("Nobody is in this team today.") }}</li>
				<li
					v-for="row in members"
					:key="row.employee"
					class="flex items-center gap-3 border-t border-outline-gray-1 px-4 py-2 first:border-t-0"
				>
					<Avatar :label="row.employee_name" :image="row.image" size="lg" />
					<div class="min-w-0 flex-1">
						<div class="truncate font-medium text-ink-gray-9">{{ row.employee_name }}</div>
						<div class="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs">
							<Badge :theme="presenceTheme(row)" :label="presenceLabel(row)" />
							<Badge v-if="row.focus" theme="blue" :label="__('In focus')" />
						</div>
					</div>
					<div class="min-w-0 max-w-[50%] text-right text-sm">
						<template v-if="row.timer">
							<div class="truncate text-ink-gray-9" :title="row.timer.project_name || row.timer.project">
								<FeatherIcon :name="row.timer.state === 'paused' ? 'pause-circle' : 'play-circle'" class="mr-1 inline h-3.5 w-3.5" />
								{{ row.timer.project_name || row.timer.project || __("No project") }}
							</div>
							<div v-if="row.timer.task" class="truncate text-xs text-ink-gray-6" :title="row.timer.task_subject">
								{{ row.timer.task_subject || row.timer.task }}
							</div>
							<div v-if="row.timer.state === 'paused'" class="text-xs text-ink-gray-5">{{ __("On a break") }}</div>
						</template>
						<span v-else class="text-xs text-ink-gray-5">{{ __("No timer running") }}</span>
					</div>
				</li>
			</ul>
		</section>
	</div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue"
import { Avatar, Badge, FeatherIcon, call } from "frappe-ui"
import IssueChatButton from "@spa/components/IssueChatButton.vue"
import { useUserRealtime } from "@spa/composables/useUserRealtime.js"
import { __ } from "@spa/utils/i18n.js"
import spaConfig from "../config"

// Live updates where realtime works; a reload every minute as the fallback (decision 2).
const REFRESH_MS = 60 * 1000

const loading = ref(true)
const error = ref("")
const team = ref("")
const members = ref([])
const updatedAt = ref(null)

const checkedIn = computed(() => members.value.filter((r) => r.presence === "checked_in").length)
const updatedLabel = computed(() =>
	updatedAt.value ? updatedAt.value.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" }) : "—"
)

function presenceLabel(row) {
	switch (row.presence) {
		case "absent":
			return __("Absent")
		case "holiday":
			return __("Public holiday")
		case "day_off":
			return __("Day off")
		case "checked_in":
			return __("Checked in since {0}", [row.since])
		default:
			return __("Not checked in")
	}
}

function presenceTheme(row) {
	if (row.presence === "checked_in") return "green"
	if (row.presence === "absent" || row.presence === "holiday" || row.presence === "day_off") return "orange"
	return "gray"
}

async function load({ quiet = false } = {}) {
	if (!quiet) loading.value = true
	error.value = ""
	try {
		const data = await call(`${spaConfig.api}.get_team_mates`)
		team.value = data.team
		members.value = data.members || []
		updatedAt.value = new Date()
	} catch (e) {
		error.value = e.messages?.[0] || e.message || __("Could not load the team mates.")
	} finally {
		loading.value = false
	}
}

// One person's new row, for the active team only.
useUserRealtime(
	"team_member_status",
	(payload) => {
		if (!payload?.row || payload.team !== team.value) return
		const index = members.value.findIndex((r) => r.employee === payload.row.employee)
		if (index >= 0) members.value.splice(index, 1, payload.row)
		updatedAt.value = new Date()
	},
	{ debounceMs: 100 }
)

let timer = null
function onVisible() {
	if (document.visibilityState === "visible") load({ quiet: true })
}
onMounted(() => {
	load()
	timer = setInterval(() => document.visibilityState === "visible" && load({ quiet: true }), REFRESH_MS)
	document.addEventListener("visibilitychange", onVisible)
})
onBeforeUnmount(() => {
	clearInterval(timer)
	document.removeEventListener("visibilitychange", onVisible)
})
</script>
