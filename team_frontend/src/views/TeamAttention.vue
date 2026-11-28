<template>
	<!-- What needs the team's attention (#2235): SLA missed or due soon, then records lying around.
	     A list of records for the team, never a figure per person. Full height; only the list scrolls. -->
	<div class="flex h-full min-h-0 flex-col bg-surface-gray-1">
		<div class="flex flex-shrink-0 flex-wrap items-center gap-2 border-b border-outline-gray-2 px-4 py-2">
			<p class="text-sm text-ink-gray-6">
				{{
					slaOn
						? __("Issues whose SLA is missed or due soon, and open Issues and Tasks of the team without activity for {0} days.", [idleDays])
						: __("Open Issues and Tasks of the team without activity for {0} days.", [idleDays])
				}}
			</p>
			<span v-if="!loading && items.length" class="ml-auto rounded bg-surface-gray-2 px-2 py-0.5 text-xs text-ink-gray-7">
				{{ truncated ? `${items.length}+` : items.length }}
			</span>
		</div>

		<div v-if="error" class="m-4 rounded-lg border border-outline-gray-2 bg-surface-red-1 p-4 text-sm text-ink-red-4">{{ error }}</div>
		<section v-else class="min-h-0 flex-1 overflow-auto">
			<div v-if="loading" class="px-4 py-10 text-center text-sm text-ink-gray-5">{{ __("Loading…") }}</div>
			<p v-else-if="!items.length" class="px-4 py-10 text-center text-sm text-ink-gray-5">
				{{ __("Nothing needs attention. Every open record of the team moved recently.") }}
			</p>
			<ul v-else class="divide-y divide-outline-gray-1 bg-surface-white">
				<li v-for="item in items" :key="`${item.doctype}:${item.name}`">
					<router-link :to="recordRoute(item)" class="flex items-start gap-3 px-4 py-2.5 hover:bg-surface-gray-1">
						<span class="mt-0.5 text-base leading-none" aria-hidden="true">{{ ICONS[item.kind] || "💤" }}</span>
						<div class="min-w-0 flex-1">
							<div class="truncate text-sm font-medium text-ink-gray-9">{{ item.title || item.name }}</div>
							<div class="mt-0.5 flex flex-wrap gap-x-3 text-xs text-ink-gray-5">
								<span :class="item.kind.endsWith('_missed') ? 'text-ink-red-4' : ''">{{ item.detail }}</span>
								<span>{{ __(item.doctype) }} {{ item.name }}</span>
								<span>{{ item.assignees.length ? item.assignees.join(", ") : __("Not assigned") }}</span>
							</div>
						</div>
					</router-link>
				</li>
			</ul>
			<p v-if="truncated" class="px-4 py-3 text-center text-xs text-ink-gray-5">
				{{ __("Only the first {0} are shown.", [items.length]) }}
			</p>
		</section>
	</div>
</template>

<script setup>
import { onMounted, ref } from "vue"
import { call } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"
import spaConfig from "../config"

// system emoji, as the cockpits use them; the text says what it is, the emoji only helps scanning
const ICONS = {
	response_missed: "⏰",
	resolution_missed: "⏰",
	response_due: "⏳",
	resolution_due: "⏳",
	idle: "💤",
}

const loading = ref(true)
const error = ref("")
const items = ref([])
const idleDays = ref(10)
const slaOn = ref(false)
const truncated = ref(false)

function recordRoute(item) {
	return item.doctype === "Task"
		? { name: "TaskDetail", params: { name: item.name } }
		: { name: "IssueDetail", params: { name: item.name } }
}

async function load() {
	try {
		const data = await call(`${spaConfig.api}.get_team_attention`)
		items.value = data.items || []
		idleDays.value = data.idle_days
		slaOn.value = data.sla_on
		truncated.value = Boolean(data.truncated)
		error.value = ""
	} catch (e) {
		error.value = e.messages?.[0] || e.message || __("Could not load what needs attention.")
	} finally {
		loading.value = false
	}
}

onMounted(load)
</script>
