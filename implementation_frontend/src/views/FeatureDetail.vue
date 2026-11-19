<template>
	<!-- One feature (#1972): what it is, the agreed definition of done, how it moved, and its GitLab issues. -->
	<div class="h-full min-h-0 overflow-y-auto bg-surface-gray-1 p-5">
		<div class="mx-auto flex max-w-4xl flex-col gap-4">
			<router-link
				:to="{ name: 'Features', params: { implementation }, query: route.query }"
				class="inline-flex items-center gap-1 self-start text-sm text-ink-gray-6 hover:text-ink-gray-9"
			>
				<FeatherIcon name="arrow-left" class="h-4 w-4" />
				{{ __("Back to the features") }}
			</router-link>

			<div v-if="error" class="rounded-lg border border-outline-gray-2 bg-surface-red-1 p-4 text-sm text-ink-red-4">{{ error }}</div>
			<div v-else-if="!feature" class="text-sm text-ink-gray-5">{{ __("Loading…") }}</div>
			<template v-else>
				<section class="rounded-lg border border-outline-gray-2 bg-surface-white p-5">
					<div class="text-xs font-semibold text-ink-gray-6">{{ feature.name }} · {{ __(feature.status) }}</div>
					<h1 class="mt-1 text-lg font-semibold text-ink-gray-9">{{ feature.title }}</h1>
					<ProgressBar class="mt-3 max-w-sm" :value="feature.progress" />
					<dl class="mt-4 grid grid-cols-1 gap-x-6 gap-y-2 text-sm sm:grid-cols-3">
						<div>
							<dt class="text-xs text-ink-gray-5">{{ __("Module") }}</dt>
							<dd class="text-ink-gray-8">{{ feature.module || "—" }}</dd>
						</div>
						<div>
							<dt class="text-xs text-ink-gray-5">{{ __("Chapter") }}</dt>
							<dd class="text-ink-gray-8">{{ feature.chapters.map((c) => c.label).join(", ") || "—" }}</dd>
						</div>
						<div>
							<dt class="text-xs text-ink-gray-5">{{ __("Release") }}</dt>
							<dd class="text-ink-gray-8">{{ feature.releases.map((r) => r.label).join(", ") || "—" }}</dd>
						</div>
						<div>
							<dt class="text-xs text-ink-gray-5">{{ __("Level (current / target)") }}</dt>
							<dd class="text-ink-gray-8">{{ feature.current_level || 0 }} / {{ feature.target_level || "—" }}</dd>
						</div>
						<div>
							<dt class="text-xs text-ink-gray-5">{{ __("Planned") }}</dt>
							<dd class="text-ink-gray-8">{{ date(feature.planned_start) }} – {{ date(feature.target_date) }}</dd>
						</div>
						<div>
							<dt class="text-xs text-ink-gray-5">{{ __("Responsible") }}</dt>
							<dd class="text-ink-gray-8">{{ feature.owner_name || "—" }}</dd>
						</div>
					</dl>
					<div v-if="feature.description" class="prose prose-sm mt-4 max-w-none text-ink-gray-8" v-html="feature.description" />
				</section>

				<section class="rounded-lg border border-outline-gray-2 bg-surface-white p-5">
					<h2 class="text-xs font-medium uppercase tracking-wide text-ink-gray-5">{{ __("Definition of done") }}</h2>
					<p v-if="feature.definition_of_done" class="mt-2 whitespace-pre-line text-sm text-ink-gray-8">{{ feature.definition_of_done }}</p>
					<p v-else class="mt-2 text-sm text-ink-gray-5">{{ __("Not written yet.") }}</p>
					<p class="mt-2 text-xs" :class="feature.dod_agreed_on ? 'text-ink-green-3' : 'text-ink-amber-3'">
						{{ feature.dod_agreed_on
							? __("Agreed on {0} with {1}", [date(feature.dod_agreed_on), feature.dod_agreed_by_name || "—"])
							: __("Not agreed yet") }}
					</p>
					<MethodNote
						class="mt-3"
						:summary="__('The definition of done says when the feature counts as finished, in words both sides agreed.')"
						:details="[
							__('It is written before the work starts, so everyone knows what “done” means and nobody argues about it later.'),
							__('When the text changes, the agreement starts again: the customer confirms the new version.'),
						]"
					/>
				</section>

				<section class="rounded-lg border border-outline-gray-2 bg-surface-white p-5">
					<h2 class="text-xs font-medium uppercase tracking-wide text-ink-gray-5">{{ __("In GitLab") }}</h2>
					<p v-if="!feature.issues.length" class="mt-2 text-sm text-ink-gray-5">{{ __("No GitLab issues linked yet.") }}</p>
					<ul v-else class="mt-2 flex flex-col">
						<li v-for="i in feature.issues" :key="i.name" class="flex flex-wrap items-center gap-3 border-t border-outline-gray-1 py-2.5 text-sm first:border-t-0">
							<FeatherIcon :name="i.state === 'closed' ? 'check-circle' : 'circle'" class="h-4 w-4 text-ink-gray-6" />
							<span class="min-w-0 flex-1 truncate text-ink-gray-9">#{{ i.issue_id }} {{ i.title }}</span>
							<span v-if="i.time_estimate_hours" class="text-xs text-ink-gray-5">{{ __("{0} h estimated", [i.time_estimate_hours]) }}</span>
							<a :href="i.issue_url" target="_blank" rel="noopener noreferrer" class="inline-flex items-center gap-1 text-xs text-ink-gray-7 underline underline-offset-2 hover:text-ink-gray-9">
								{{ __("Open in GitLab") }}
								<FeatherIcon name="external-link" class="h-3 w-3" />
							</a>
						</li>
					</ul>
				</section>

				<section v-if="feature.doctypes.length" class="rounded-lg border border-outline-gray-2 bg-surface-white p-5">
					<h2 class="text-xs font-medium uppercase tracking-wide text-ink-gray-5">{{ __("What we build") }}</h2>
					<ul class="mt-2 flex flex-col">
						<li v-for="d in feature.doctypes" :key="d.name" class="border-t border-outline-gray-1 py-2 text-sm first:border-t-0">
							<span class="font-medium text-ink-gray-9">{{ d.name }}</span>
							<span v-if="d.kind" class="text-xs text-ink-gray-5"> · {{ __(d.kind) }}</span>
							<p v-if="d.work_done" class="mt-0.5 text-ink-gray-7">{{ d.work_done }}</p>
						</li>
					</ul>
				</section>

				<section v-if="feature.history.length" class="rounded-lg border border-outline-gray-2 bg-surface-white p-5">
					<h2 class="text-xs font-medium uppercase tracking-wide text-ink-gray-5">{{ __("History") }}</h2>
					<ul class="mt-2 flex flex-col">
						<li v-for="(h, index) in feature.history" :key="index" class="flex flex-wrap gap-x-3 border-t border-outline-gray-1 py-2 text-sm first:border-t-0">
							<span class="w-24 text-ink-gray-5">{{ date(h.date) }}</span>
							<span class="text-ink-gray-8">{{ __(h.status) }}<template v-if="h.level"> · {{ __("level {0}", [h.level]) }}</template></span>
							<span v-if="h.by" class="text-ink-gray-5">{{ h.by }}</span>
							<span v-if="h.note" class="w-full pl-24 text-ink-gray-7">{{ h.note }}</span>
						</li>
					</ul>
				</section>
			</template>
		</div>
	</div>
</template>

<script setup>
import { ref, watch } from "vue"
import { useRoute } from "vue-router"
import dayjs from "dayjs"
import { call, FeatherIcon } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"
import MethodNote from "../components/MethodNote.vue"
import ProgressBar from "../components/ProgressBar.vue"
import spaConfig from "../config"

const props = defineProps({
	implementation: { type: String, required: true },
	feature: { type: String, required: true },
})

const route = useRoute()
const feature = ref(null)
const error = ref("")

watch(
	() => [props.implementation, props.feature],
	async () => {
		feature.value = null
		error.value = ""
		try {
			feature.value = await call(`${spaConfig.api}.get_feature`, { implementation: props.implementation, name: props.feature })
		} catch (e) {
			error.value = e?.messages?.[0] || e?.message || __("Could not load the feature")
		}
	},
	{ immediate: true }
)

function date(value) {
	return value ? dayjs(value).format("D MMM YYYY") : "—"
}
</script>
