<template>
	<div>
		<div class="relative">
			<div ref="clipEl" :class="expanded ? '' : maxHeightClass" class="overflow-hidden">
				<!--
					The sender's own HTML. Already stripped of script/style and limited
					to an allowlist of CSS server-side (clean_email_html), so the
					message keeps its formatting without being trusted markup.
				-->
				<div ref="contentEl" class="email-body" v-html="html" />
			</div>
			<!-- Only when there really is more below, so a short mail isn't washed out. -->
			<div
				v-if="clipped && !expanded"
				class="pointer-events-none absolute inset-x-0 bottom-0 h-8 bg-gradient-to-t from-white to-transparent dark:from-gray-900"
			/>
		</div>
		<button
			v-if="clipped"
			type="button"
			class="mt-1 text-xs font-medium text-ink-gray-6 hover:text-ink-gray-9"
			@click="expanded = !expanded"
		>
			{{ expanded ? "Show less" : "Show full message" }}
		</button>
	</div>
</template>

<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"

const props = defineProps({
	html: { type: String, default: "" },
	/** Generous by default: the point is to read the mail, not to guess at it. */
	maxHeightClass: { type: String, default: "max-h-[30vh]" },
})

const clipEl = ref(null)
const contentEl = ref(null)
const clipped = ref(false)
const expanded = ref(false)

function measure() {
	// While expanded the clip is lifted, so there's nothing to compare against —
	// keep the flag that got us here so "Show less" stays available.
	if (expanded.value) return
	const clip = clipEl.value
	const content = contentEl.value
	if (!clip || !content) return
	clipped.value = content.scrollHeight > clip.clientHeight + 4
}

let observer = null

onMounted(() => {
	// Images and remote content settle after the first paint, so watch the
	// element rather than measuring once.
	if (typeof ResizeObserver !== "undefined") {
		observer = new ResizeObserver(() => measure())
		if (contentEl.value) observer.observe(contentEl.value)
	}
	nextTick(measure)
})

onBeforeUnmount(() => observer?.disconnect())

watch(
	() => props.html,
	() => {
		expanded.value = false
		clipped.value = false
		nextTick(measure)
	}
)
</script>

<style scoped>
/*
 * Keep the sender's formatting — lists, emphasis, links, tables — and impose
 * only enough to stop a wide table or an oversized image breaking the column.
 */
.email-body {
	font-size: 0.8125rem;
	line-height: 1.55;
	color: var(--ink-gray-7, #4a4a48);
	overflow-wrap: anywhere;
}

.email-body :deep(p),
.email-body :deep(ul),
.email-body :deep(ol),
.email-body :deep(blockquote) {
	margin: 0 0 0.5em;
}

.email-body :deep(ul),
.email-body :deep(ol) {
	padding-left: 1.25em;
	list-style: revert;
}

.email-body :deep(blockquote) {
	border-left: 2px solid var(--outline-gray-2, #e2e2e0);
	padding-left: 0.75em;
	color: var(--ink-gray-5, #7c7c78);
}

.email-body :deep(a) {
	color: var(--ink-blue-3, #2570d4);
	text-decoration: underline;
}

.email-body :deep(img) {
	max-width: 100%;
	height: auto;
}

.email-body :deep(table) {
	display: block;
	max-width: 100%;
	overflow-x: auto;
	border-collapse: collapse;
}

.email-body :deep(th),
.email-body :deep(td) {
	border: 1px solid var(--outline-gray-2, #e2e2e0);
	padding: 0.25em 0.5em;
}

.email-body :deep(h1),
.email-body :deep(h2),
.email-body :deep(h3) {
	margin: 0 0 0.4em;
	font-size: 0.875rem;
	font-weight: 600;
}
</style>
