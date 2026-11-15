<template>
	<section class="space-y-2.5" :aria-label="__('Phriend report')">
		<div class="flex items-center gap-2">
			<PhriendMark size="md" />
			<span class="text-[11px] font-semibold uppercase tracking-wide text-ink-gray-6">
				{{ __("Phriend report") }}
			</span>
			<Badge
				class="ml-auto"
				:label="typeLabel(report.type)"
				:theme="typeTheme(report.type)"
				size="sm"
				variant="subtle"
			/>
		</div>

		<button
			v-if="report.screenshot && !brokenImage"
			type="button"
			class="group relative block w-full overflow-hidden rounded-md border border-outline-gray-2 bg-surface-gray-1 focus:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
			:title="__('Enlarge the screenshot')"
			@click="enlarged = true"
		>
			<img
				:src="report.screenshot"
				:alt="__('Screenshot of the reported page')"
				class="block max-h-44 w-full object-cover object-top"
				loading="lazy"
				@error="brokenImage = true"
			/>
			<span
				class="absolute right-1.5 top-1.5 rounded bg-surface-white/90 p-1 text-ink-gray-7 opacity-0 shadow-sm transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100"
			>
				<FeatherIcon name="maximize-2" class="h-3.5 w-3.5" />
			</span>
		</button>
		<p v-else class="text-xs text-ink-gray-6">
			{{ report.screenshot ? __("The screenshot can't be shown.") : __("Sent without a screenshot.") }}
		</p>

		<p class="text-xs text-ink-gray-6">
			{{ __("Reported by {0}", [report.reported_by_name || report.reported_by || "—"]) }}
			· {{ formatDatetime(report.reported_at) }}
		</p>

		<div class="space-y-0.5">
			<a
				v-if="report.page_url"
				:href="report.page_url"
				target="_blank"
				rel="noopener"
				class="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm font-medium text-ink-gray-8 hover:bg-surface-gray-2 hover:text-ink-gray-9"
				:title="report.page_url"
			>
				<FeatherIcon name="external-link" class="h-4 w-4 flex-shrink-0" />
				<span class="truncate">{{ __("Open the page") }}</span>
			</a>
			<a
				v-if="report.ref_url"
				:href="report.ref_url"
				target="_blank"
				rel="noopener"
				class="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm text-ink-gray-8 hover:bg-surface-gray-2 hover:text-ink-gray-9"
				:title="`${__(report.ref_doctype)}: ${report.ref_docname}`"
			>
				<FeatherIcon name="file-text" class="h-4 w-4 flex-shrink-0" />
				<span class="truncate">{{ __(report.ref_doctype) }}: {{ report.ref_docname }}</span>
			</a>
		</div>

		<details class="group rounded-md text-xs text-ink-gray-7">
			<summary
				class="flex cursor-pointer list-none items-start gap-1.5 rounded-md px-2 py-1.5 hover:bg-surface-gray-2 [&::-webkit-details-marker]:hidden"
			>
				<FeatherIcon
					name="chevron-right"
					class="mt-px h-3.5 w-3.5 flex-shrink-0 transition-transform group-open:rotate-90"
				/>
				<span class="min-w-0">
					<span class="block font-medium text-ink-gray-8">{{ __("Technical details") }}</span>
					<span class="block text-ink-gray-6">{{ detailsSummary(details) }}</span>
				</span>
			</summary>
			<dl class="mt-1 space-y-2 px-2 pb-1">
				<div v-for="row in detailRows" :key="row.label">
					<dt class="font-medium text-ink-gray-6">{{ row.label }}</dt>
					<dd class="break-words text-ink-gray-8">{{ row.value }}</dd>
				</div>
				<div v-for="list in entryLists" :key="list.label">
					<dt class="font-medium text-ink-gray-6">{{ list.label }}</dt>
					<dd>
						<ul class="space-y-1">
							<li
								v-for="(entry, i) in list.entries"
								:key="i"
								class="break-words font-mono text-[11px] leading-snug text-ink-gray-8"
							>
								{{ entryLine(entry) }}
							</li>
						</ul>
					</dd>
				</div>
			</dl>
		</details>
	</section>

	<Dialog v-model="enlarged" :options="{ title: __('Screenshot'), size: '7xl' }">
		<template #body-content>
			<img
				:src="report.screenshot"
				:alt="__('Screenshot of the reported page')"
				class="block h-auto w-full rounded-md border border-outline-gray-2"
			/>
		</template>
	</Dialog>
</template>

<script setup>
// The Phriend report of an Issue, in the Issue page's side panel (#1901). The reporter's comment
// is not repeated here: it is in the Issue description.
import { computed, ref, watch } from "vue"
import { Badge, Dialog, FeatherIcon } from "frappe-ui"
import PhriendMark from "@spa/components/PhriendMark.vue"
import { __ } from "@spa/utils/i18n.js"
import { formatDatetime } from "@spa/utils/datetime.js"
import { detailsSummary, entryLine, typeLabel, typeTheme, versionsLine } from "@spa/utils/phriendReport.js"

const props = defineProps({
	// get_issue's `phriend` block: see phamos/phriend/report.py
	report: { type: Object, required: true },
})

const enlarged = ref(false)
const brokenImage = ref(false)
watch(
	() => props.report.screenshot,
	() => (brokenImage.value = false),
)

const details = computed(() => props.report.details || {})

const detailRows = computed(() => {
	const d = details.value
	return [
		{ label: __("Browser"), value: d.browser },
		{ label: __("Screen"), value: d.viewport },
		{ label: __("Reported from"), value: [__(d.app || ""), props.report.route].filter(Boolean).join(" · ") },
		{ label: __("Language"), value: d.lang },
		{ label: __("Versions"), value: versionsLine(d.versions) },
	].filter((row) => row.value)
})

const entryLists = computed(() =>
	[
		{ label: __("Recent errors"), entries: details.value.recent_errors || [] },
		{ label: __("Failed requests"), entries: details.value.failed_requests || [] },
	].filter((list) => list.entries.length),
)
</script>
