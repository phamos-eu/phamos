<template>
	<div class="flex h-full min-h-0 bg-surface-gray-1">
		<div class="h-full min-h-0 flex-1 overflow-y-auto p-5">
			<div class="flex flex-col gap-5">
				<!-- Hand in for vote (#1842). The page title ("Ideas for vote") is in the cockpit header. -->
				<p class="text-sm text-ink-gray-6">
					{{ __("Ideas your colleagues handed in. Vote for the ones you want to see happen.") }}
				</p>

				<div v-if="voteIdeas.error" class="rounded-lg border border-outline-gray-2 bg-surface-red-1 p-4 text-sm text-ink-red-4">
					{{ voteIdeas.error }}
				</div>
				<div v-else-if="!voteIdeas.loaded" class="flex min-h-64 items-center justify-center text-sm text-ink-gray-5">
					{{ __("Loading the ideas up for vote…") }}
				</div>
				<section v-else class="rounded-lg border border-outline-gray-2 bg-surface-white">
					<p v-if="!voteIdeas.rows.length" class="px-4 py-10 text-center text-sm text-ink-gray-5">
						{{ __("No idea is up for vote right now. Hand one of yours in from its page.") }}
					</p>
					<ul v-else class="divide-y divide-outline-gray-1">
						<li v-for="row in voteIdeas.rows" :key="row.name" class="flex items-start gap-3 px-4 py-3 hover:bg-surface-gray-1">
							<router-link
								:to="{ name: 'IdeaVoteDetail', params: { name: row.name } }"
								data-list-item
								class="flex min-w-0 flex-1 flex-col gap-2 focus:outline-none focus-visible:bg-surface-gray-2"
							>
								<span class="truncate text-sm font-medium text-ink-gray-9">{{ row.title }}</span>
								<p v-if="excerpt(row)" class="line-clamp-2 text-sm text-ink-gray-5">{{ excerpt(row) }}</p>
								<div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-gray-5">
									<span v-if="row.author" class="inline-flex items-center gap-1.5">
										<UserAvatar :name="row.author.name" :label="row.author.full_name" :image="row.author.user_image || ''" size="xs" />
										{{ row.author.full_name }}
									</span>
									<span v-if="row.handed_in_on">{{ __("Handed in {0}", [formatDatetime(row.handed_in_on)]) }}</span>
									<span class="text-ink-gray-6">{{ __(row.stage) }}</span>
								</div>
							</router-link>
							<VoteButton :row="row" />
						</li>
					</ul>
				</section>
			</div>
		</div>
	</div>
</template>

<script setup>
import { onBeforeUnmount, onMounted } from "vue"
import UserAvatar from "@spa/components/UserAvatar.vue"
import { useUserRealtime } from "@spa/composables/useUserRealtime.js"
import { formatDatetime } from "@spa/utils/datetime.js"
import { __ } from "@spa/utils/i18n.js"
import { summaryWithoutTitle } from "@spa/utils/ideaSummary.js"
import VoteButton from "../components/IdeaVoteButton.vue"
import { loadIdeasForVote, resetVoteQueue, voteIdeas } from "../ideasStore.js"

const excerpt = (row) => summaryWithoutTitle(row.summary, row.title)

// Votes and hand-ins from everyone; the event carries no content, so the list reloads.
useUserRealtime("cockpit_idea_vote_changed", loadIdeasForVote, { debounceMs: 300 })

function onVisible() {
	if (document.visibilityState === "visible") loadIdeasForVote()
}

onMounted(() => {
	// Back on the list: the next idea opened starts a fresh walk in the list's current order.
	resetVoteQueue()
	loadIdeasForVote()
	document.addEventListener("visibilitychange", onVisible)
})
onBeforeUnmount(() => document.removeEventListener("visibilitychange", onVisible))
</script>
