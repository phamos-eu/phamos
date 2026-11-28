<template>
	<!-- One feature beside the list or board (#1972): what it is, the agreed definition of done, its
	     GitLab issues and how it moved. The panel scrolls on its own; the page around it stays put. -->
	<aside class="flex min-h-0 flex-col rounded-lg border border-outline-gray-2 bg-surface-white" :aria-label="__('Feature')">
		<div class="flex items-start gap-2 border-b border-outline-gray-1 px-4 py-2.5">
			<div class="min-w-0 flex-1">
				<div class="text-xs text-ink-gray-5">{{ feature }}<template v-if="data"> · <StatusBadge :status="data.status" /></template></div>
				<h2 class="mt-0.5 text-base font-semibold leading-snug text-ink-gray-9">{{ data?.title || "…" }}</h2>
			</div>
			<button type="button" class="rounded p-1 text-ink-gray-5 hover:bg-surface-gray-2 hover:text-ink-gray-9" :aria-label="__('Close')" :title="__('Close (Esc)')" @click="$emit('close')">
				<FeatherIcon name="x" class="h-4 w-4" />
			</button>
		</div>

		<div v-if="error" class="m-4 rounded-lg bg-surface-red-1 p-3 text-sm text-ink-red-4">{{ error }}</div>
		<div v-else-if="!data" class="p-4 text-sm text-ink-gray-5">{{ __("Loading…") }}</div>
		<div v-else class="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-4 py-3 text-sm">
			<ProgressBar :value="data.progress" />
			<dl class="grid grid-cols-2 gap-x-4 gap-y-1.5">
				<div v-for="fact in facts" :key="fact.label" class="min-w-0">
					<dt class="text-xs text-ink-gray-5">{{ fact.label }}</dt>
					<dd class="truncate text-ink-gray-8" :title="fact.value">{{ fact.value }}</dd>
				</div>
			</dl>
			<div v-if="data.description" class="prose prose-sm max-w-none text-ink-gray-8" v-html="data.description" />

			<section>
				<h3 class="text-xs font-medium uppercase tracking-wide text-ink-gray-5">{{ __("Definition of done") }}</h3>
				<p v-if="data.definition_of_done" class="mt-1 whitespace-pre-line text-ink-gray-8">{{ data.definition_of_done }}</p>
				<p v-else class="mt-1 text-ink-gray-5">{{ __("Not written yet.") }}</p>
				<p class="mt-1 text-xs" :class="data.dod_agreed_on ? 'text-ink-green-3' : 'text-ink-amber-3'">
					{{ data.dod_agreed_on ? __("Agreed on {0} with {1}", [date(data.dod_agreed_on), data.dod_agreed_by_name || "—"]) : __("Not agreed yet") }}
				</p>
				<MethodNote
					inline
					class="mt-1"
					:summary="__('The definition of done says when the feature counts as finished, in words both sides agreed.')"
					:details="[
						__('It is written before the work starts, so everyone knows what “done” means and nobody argues about it later.'),
						__('When the text changes, the agreement starts again: the customer confirms the new version.'),
					]"
				/>
			</section>

			<section>
				<h3 class="text-xs font-medium uppercase tracking-wide text-ink-gray-5">{{ __("In GitLab") }}</h3>
				<p v-if="!data.issues.length" class="mt-1 text-ink-gray-5">{{ __("No GitLab issues linked yet.") }}</p>
				<a
					v-for="i in data.issues"
					:key="i.name"
					:href="i.issue_url"
					target="_blank"
					rel="noopener noreferrer"
					class="flex items-center gap-2 py-0.5 text-ink-gray-8 hover:text-ink-gray-9"
					:title="__('Open in GitLab')"
				>
					<FeatherIcon :name="i.state === 'closed' ? 'check-circle' : 'circle'" class="h-3.5 w-3.5 shrink-0 text-ink-gray-5" />
					<span class="min-w-0 flex-1 truncate">#{{ i.issue_id }} {{ i.title }}</span>
					<span v-if="i.time_estimate_hours" class="shrink-0 text-xs text-ink-gray-5">{{ i.time_estimate_hours }} h</span>
					<FeatherIcon name="external-link" class="h-3 w-3 shrink-0 text-ink-gray-5" />
				</a>
			</section>

			<section v-if="data.doctypes.length">
				<h3 class="text-xs font-medium uppercase tracking-wide text-ink-gray-5">{{ __("What we build") }}</h3>
				<div v-for="d in data.doctypes" :key="d.name" class="py-0.5">
					<span class="text-ink-gray-9">{{ d.name }}</span>
					<span v-if="d.kind" class="text-xs text-ink-gray-5"> · {{ __(d.kind) }}</span>
					<span v-if="d.work_done" class="text-ink-gray-7"> – {{ d.work_done }}</span>
				</div>
			</section>

			<section v-if="data.history.length">
				<h3 class="text-xs font-medium uppercase tracking-wide text-ink-gray-5">{{ __("History") }}</h3>
				<div v-for="(h, index) in shownHistory" :key="index" class="flex gap-2 py-0.5 text-ink-gray-8">
					<span class="w-24 shrink-0 text-ink-gray-5">{{ date(h.date) }}</span>
					<span class="min-w-0 flex-1 truncate" :title="h.note">
						{{ __(h.status) }}<template v-if="h.level"> · {{ __("level {0}", [h.level]) }}</template><template v-if="h.by"> · {{ h.by }}</template>
					</span>
				</div>
				<button v-if="data.history.length > 3" type="button" class="mt-0.5 text-xs text-ink-gray-6 underline underline-offset-2" @click="allHistory = !allHistory">
					{{ allHistory ? __("Show less") : __("Show all {0}", [data.history.length]) }}
				</button>
			</section>
		</div>
	</aside>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import dayjs from "dayjs"
import { call, FeatherIcon } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"
import MethodNote from "./MethodNote.vue"
import ProgressBar from "./ProgressBar.vue"
import StatusBadge from "./StatusBadge.vue"
import spaConfig from "../config"

const props = defineProps({
	implementation: { type: String, required: true },
	feature: { type: String, required: true },
})
defineEmits(["close"])

const data = ref(null)
const error = ref("")
const allHistory = ref(false)

watch(
	() => [props.implementation, props.feature],
	async () => {
		data.value = null
		error.value = ""
		try {
			data.value = await call(`${spaConfig.api}.get_feature`, { implementation: props.implementation, name: props.feature })
		} catch (e) {
			error.value = e?.messages?.[0] || e?.message || __("Could not load the feature")
		}
	},
	{ immediate: true }
)

const facts = computed(() => {
	const f = data.value
	return [
		{ label: __("Module"), value: f.module || "—" },
		{ label: __("Responsible"), value: f.owner_name || "—" },
		{ label: __("Chapter"), value: f.chapters.map((c) => c.label).join(", ") || "—" },
		{ label: __("Release"), value: f.releases.map((r) => r.label).join(", ") || "—" },
		{ label: __("Level (current / target)"), value: `${f.current_level || 0} / ${f.target_level || "—"}` },
		{ label: __("Worked"), value: f.touch_hours ? `${f.touch_hours} h` : "—" },
		{ label: __("Planned"), value: f.planned_start || f.target_date ? `${date(f.planned_start)} – ${date(f.target_date)}` : "—" },
	]
})
const shownHistory = computed(() => (allHistory.value ? data.value.history : data.value.history.slice(0, 3)))

function date(value) {
	return value ? dayjs(value).format("D MMM YYYY") : "—"
}
</script>
