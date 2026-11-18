<template>
	<!-- Links: the /timesheet "Project Links" tab. Still the Implementation's free-text field; #1682 makes it a table. -->
	<div class="h-full min-h-0 overflow-y-auto bg-surface-gray-1 p-5">
		<div class="mx-auto flex max-w-3xl flex-col gap-5">
			<div v-if="error" class="rounded-lg border border-outline-gray-2 bg-surface-red-1 p-4 text-sm text-ink-red-4">
				{{ error }}
			</div>
			<section v-else class="rounded-lg border border-outline-gray-2 bg-surface-white p-5">
				<h2 class="text-xs font-medium uppercase tracking-wide text-ink-gray-5">{{ __("Your systems and links") }}</h2>
				<div v-if="loading" class="mt-3 text-sm text-ink-gray-5">{{ __("Loading…") }}</div>
				<!-- Sanitized on the server (get_links). -->
				<div v-else-if="html" ref="content" class="cockpit-links prose prose-sm mt-3 max-w-none text-ink-gray-8" v-html="html" />
				<p v-else class="mt-3 text-sm text-ink-gray-5">{{ __("No links added yet. Your project manager will add them here.") }}</p>
			</section>
		</div>
	</div>
</template>

<script setup>
import { nextTick, ref, watch } from "vue"
import { call } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"
import spaConfig from "../config"

const props = defineProps({ implementation: { type: String, required: true } })

const html = ref("")
const loading = ref(false)
const error = ref("")
const content = ref(null)

watch(
	() => props.implementation,
	async (implementation) => {
		loading.value = true
		error.value = ""
		html.value = ""
		try {
			const data = await call(`${spaConfig.api}.get_links`, { implementation })
			html.value = data?.html || ""
			loading.value = false
			await nextTick()
			for (const a of content.value?.querySelectorAll("a[href]") || []) {
				a.target = "_blank"
				a.rel = "noopener noreferrer"
			}
		} catch (e) {
			error.value = e?.message || __("Could not load the links")
		} finally {
			loading.value = false
		}
	},
	{ immediate: true }
)
</script>

<style scoped>
/* Links open in a new tab without access to this window. */
.cockpit-links :deep(a) {
	text-decoration: underline;
	text-underline-offset: 3px;
}
</style>
