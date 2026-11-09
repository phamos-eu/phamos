<template>
	<div class="flex h-full min-h-0 bg-surface-gray-1">
		<div class="h-full min-h-0 flex-1 overflow-y-auto p-5">
			<div class="flex flex-col gap-4">
				<!-- A colleague's idea up for vote (#1842): read only, without its history or sessions. -->
				<router-link :to="{ name: 'IdeasVote' }" class="self-start text-xs text-ink-gray-5 hover:text-ink-gray-8">
					{{ __("All ideas up for vote") }}
				</router-link>

				<div v-if="error" class="rounded-lg border border-outline-gray-2 bg-surface-white p-4 text-sm text-ink-gray-6">
					{{ error }}
				</div>
				<div v-else-if="!idea" class="flex min-h-64 items-center justify-center text-sm text-ink-gray-5">
					{{ __("Loading the idea…") }}
				</div>
				<template v-else>
					<div class="flex flex-wrap items-start justify-between gap-3">
						<h1 class="min-w-0 flex-1 py-1 text-2xl font-semibold tracking-tight text-ink-gray-9">{{ idea.title }}</h1>
						<div class="flex items-center gap-3 pt-2">
							<router-link v-if="idea.mine" :to="{ name: 'IdeaDetail', params: { name: idea.name } }" class="text-xs text-ink-gray-5 hover:text-ink-gray-8">
								{{ __("Open in My Ideas") }}
							</router-link>
							<VoteButton :row="idea" @voted="onVoted" @withdrawn="onWithdrawn" />
						</div>
					</div>
					<div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-gray-5">
						<span v-if="idea.author" class="inline-flex items-center gap-1.5">
							<UserAvatar :name="idea.author.name" :label="idea.author.full_name" :image="idea.author.user_image || ''" size="xs" />
							{{ idea.author.full_name }}
						</span>
						<span v-if="idea.handed_in_on">{{ __("Handed in {0}", [formatDatetime(idea.handed_in_on)]) }}</span>
						<span class="inline-flex items-center gap-1 text-ink-gray-6">
							<StageIcon :name="idea.stage" class="h-3 w-3" />{{ __(idea.stage) }}
						</span>
						<span>{{ voteLabel(idea.vote_count) }}</span>
					</div>
					<!-- Text Editor HTML, sanitized by Frappe on every save. -->
					<section class="rounded-lg border border-outline-gray-2 bg-surface-white p-4">
						<div v-if="idea.content" class="prose prose-sm max-w-none text-ink-gray-8" v-html="idea.content" />
						<p v-else class="text-sm text-ink-gray-5">{{ __("This idea has no text yet.") }}</p>
					</section>
				</template>
			</div>
		</div>
	</div>
</template>

<script setup>
import { onMounted, ref, watch } from "vue"
import { useRouter } from "vue-router"
import { call } from "frappe-ui"
import StageIcon from "@spa/components/StageIcon.vue"
import UserAvatar from "@spa/components/UserAvatar.vue"
import { useUserRealtime } from "@spa/composables/useUserRealtime.js"
import { formatDatetime } from "@spa/utils/datetime.js"
import { __ } from "@spa/utils/i18n.js"
import { notify } from "@spa/utils/notify.js"
import VoteButton from "../components/IdeaVoteButton.vue"
import spaConfig from "../config"
import { voteLabel } from "../ideasStore.js"

const props = defineProps({ name: { type: String, required: true } })
const router = useRouter()
const idea = ref(null)
const error = ref("")

async function load(name) {
	error.value = ""
	try {
		idea.value = await call(`${spaConfig.api}.get_idea_for_vote`, { name })
	} catch (e) {
		idea.value = null
		error.value = __("This idea is no longer up for vote.")
	}
}

// My own idea taken off the vote: back to it in My Ideas.
function onWithdrawn(doc) {
	router.push({ name: "IdeaDetail", params: { name: doc.name } })
}

function onVoted(result) {
	if (idea.value) Object.assign(idea.value, { voted: result.voted, vote_count: result.vote_count })
}

useUserRealtime(
	"cockpit_idea_vote_changed",
	(payload) => {
		if (!idea.value || payload?.name !== idea.value.name) return
		if (!payload.vote_status) {
			if (idea.value.mine) return
			notify.success(__("This idea is no longer up for vote."))
			router.push({ name: "IdeasVote" })
			return
		}
		idea.value.vote_count = payload.vote_count
	},
	{ debounceMs: 200 }
)

watch(() => props.name, load)
onMounted(() => load(props.name))
</script>
