<template>
	<!-- Ideas shared with the team (#1980): the list, and the open idea in a side panel with its vote
	     and chat. Full height; only the list and the panel scroll. -->
	<div class="flex h-full min-h-0 flex-col bg-surface-gray-1">
		<div class="flex flex-shrink-0 flex-wrap items-center gap-2 border-b border-outline-gray-2 px-4 py-2">
			<p class="text-sm text-ink-gray-6">{{ __("Ideas shared with {0}: the same vote as the company's, read by the team only.", [team || __("the team")]) }}</p>
			<Button class="ml-auto" variant="solid" size="sm" @click="newIdeaOpen = true">
				<template #prefix><FeatherIcon name="plus" class="h-3.5 w-3.5" /></template>
				{{ __("New team idea") }}
			</Button>
		</div>

		<div v-if="error" class="m-4 rounded-lg border border-outline-gray-2 bg-surface-red-1 p-4 text-sm text-ink-red-4">{{ error }}</div>
		<div v-else class="flex min-h-0 flex-1">
			<section class="min-h-0 min-w-0 flex-1 overflow-auto">
				<div v-if="loading" class="px-4 py-10 text-center text-sm text-ink-gray-5">{{ __("Loading ideas…") }}</div>
				<p v-else-if="!ideas.length" class="px-4 py-10 text-center text-sm text-ink-gray-5">
					{{ __("No idea is shared with the team yet. Share one of yours from your Personal Cockpit, or start a new one here.") }}
				</p>
				<ul v-else class="divide-y divide-outline-gray-1">
					<li
						v-for="row in ideas"
						:key="row.name"
						class="flex cursor-pointer items-start gap-3 px-4 py-2.5 hover:bg-surface-white"
						:class="{ 'bg-surface-white': row.name === selected }"
						@click="open(row.name)"
					>
						<div class="min-w-0 flex-1">
							<div class="truncate text-sm font-medium text-ink-gray-9">{{ row.title }}</div>
							<p v-if="row.summary" class="line-clamp-2 text-xs text-ink-gray-5">{{ row.summary }}</p>
							<div class="mt-0.5 text-xs text-ink-gray-5">
								<span v-if="row.author">{{ row.author.full_name }} · </span>{{ __(row.stage) }}
							</div>
						</div>
						<Button
							size="sm"
							:variant="row.voted ? 'solid' : 'subtle'"
							:disabled="row.mine"
							:title="row.mine ? __('You cannot vote for your own idea.') : ''"
							@click.stop="vote(row)"
						>
							<template #prefix><FeatherIcon name="thumbs-up" class="h-3.5 w-3.5" /></template>
							{{ row.vote_count }}
						</Button>
					</li>
				</ul>
			</section>

			<aside v-if="detail" class="flex min-h-0 w-full max-w-xl flex-col border-l border-outline-gray-2 bg-surface-white">
				<div class="flex items-start gap-2 border-b border-outline-gray-1 px-4 py-3">
					<div class="min-w-0 flex-1">
						<h2 class="truncate text-base font-semibold text-ink-gray-9">{{ detail.title }}</h2>
						<div class="text-xs text-ink-gray-5">
							<span v-if="detail.author">{{ detail.author.full_name }} · </span>{{ __(detail.stage) }} · {{ voteLabel(detail.vote_count) }}
						</div>
					</div>
					<Button variant="ghost" size="sm" :aria-label="__('Close')" @click="close"><FeatherIcon name="x" class="h-4 w-4" /></Button>
				</div>
				<div class="flex flex-wrap items-center gap-2 px-4 py-2">
					<Button :variant="detail.voted ? 'solid' : 'subtle'" :disabled="detail.mine" @click="vote(detail)">
						<template #prefix><FeatherIcon name="thumbs-up" class="h-4 w-4" /></template>
						{{ detail.voted ? __("Voted") : __("Vote") }}
					</Button>
					<IssueChatButton v-if="detail.chat_enabled" doctype="Idea" :record-name="detail.name" :subject="detail.title" :api="spaConfig.api" />
					<a v-if="detail.mine" :href="`/personal-cockpit/ideas/${encodeURIComponent(detail.name)}`" class="ml-auto text-xs text-ink-gray-5 hover:text-ink-gray-8">
						{{ __("Edit in my Personal Cockpit") }}
					</a>
				</div>
				<!-- Text Editor HTML, sanitized by Frappe on every save (as on the Personal Cockpit's vote page). -->
				<div class="prose prose-sm min-h-0 flex-1 overflow-auto px-4 pb-4 text-ink-gray-8" v-html="detail.content" />
			</aside>
		</div>

		<Dialog v-model="newIdeaOpen" :options="{ title: __('New team idea'), size: 'md' }">
			<template #body-content>
				<form class="space-y-3" @submit.prevent="createIdea">
					<FormControl v-model="newTitle" :label="__('Title')" type="text" size="sm" required />
					<p class="text-xs text-ink-gray-5">{{ __("It is your idea: you write it out in your Personal Cockpit. Your team can read it, vote and chat right away.") }}</p>
				</form>
			</template>
			<template #actions>
				<div class="flex justify-end gap-2">
					<Button variant="subtle" @click="newIdeaOpen = false">{{ __("Close") }}</Button>
					<Button variant="solid" :loading="creating" :disabled="!newTitle.trim()" @click="createIdea">{{ __("Share with team") }}</Button>
				</div>
			</template>
		</Dialog>
	</div>
</template>

<script setup>
import { onMounted, ref } from "vue"
import { Button, Dialog, FeatherIcon, FormControl, call } from "frappe-ui"
import IssueChatButton from "@spa/components/IssueChatButton.vue"
import { useUserRealtime } from "@spa/composables/useUserRealtime.js"
import { __ } from "@spa/utils/i18n.js"
import { notify } from "@spa/utils/notify.js"
import spaConfig from "../config"

const loading = ref(true)
const error = ref("")
const team = ref("")
const ideas = ref([])
const selected = ref(null)
const detail = ref(null)
const newIdeaOpen = ref(false)
const newTitle = ref("")
const creating = ref(false)

function voteLabel(count) {
	return count === 1 ? __("1 vote") : __("{0} votes", [count || 0])
}

async function load() {
	try {
		const data = await call(`${spaConfig.api}.get_team_ideas`)
		team.value = data.team
		ideas.value = data.ideas || []
		error.value = ""
	} catch (e) {
		error.value = e.messages?.[0] || e.message || __("Could not load the ideas.")
	} finally {
		loading.value = false
	}
}

async function open(name) {
	selected.value = name
	try {
		detail.value = await call(`${spaConfig.api}.get_idea_for_vote`, { name })
	} catch (e) {
		notify.error(__("Could not open the idea"), e.messages?.[0] || e.message || "")
	}
}

function close() {
	selected.value = null
	detail.value = null
}

async function vote(row) {
	if (row.mine) return
	try {
		const result = await call(`${spaConfig.api}.vote_idea`, { name: row.name })
		for (const target of [ideas.value.find((r) => r.name === row.name), detail.value?.name === row.name ? detail.value : null]) {
			if (target) Object.assign(target, { voted: result.voted, vote_count: result.vote_count })
		}
	} catch (e) {
		notify.error(__("Could not vote"), e.messages?.[0] || e.message || "")
	}
}

async function createIdea() {
	if (!newTitle.value.trim()) return
	creating.value = true
	try {
		const doc = await call(`${spaConfig.api}.create_team_idea`, { title: newTitle.value.trim() })
		newIdeaOpen.value = false
		newTitle.value = ""
		await load()
		open(doc.name)
	} catch (e) {
		notify.error(__("Could not create the idea"), e.messages?.[0] || e.message || "")
	} finally {
		creating.value = false
	}
}

// votes and shares of others reach the list (the same event the Personal Cockpit's vote list uses)
useUserRealtime("cockpit_idea_vote_changed", load, { debounceMs: 300 })

onMounted(load)
</script>
