<template>
	<div class="flex items-center gap-1" role="search">
		<div class="relative">
			<FeatherIcon name="search" class="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-gray-4" />
			<input
				ref="input"
				v-model="query"
				type="search"
				class="h-7 w-40 rounded border-none bg-surface-gray-2 pl-7 pr-14 text-sm text-ink-gray-8 placeholder-ink-gray-4 focus:bg-surface-gray-3 focus:ring-0 lg:w-56"
				placeholder="Search this page  /"
				aria-label="Search this page"
				@keydown.enter.prevent="step($event.shiftKey ? -1 : 1)"
				@keydown.esc.prevent="clear"
			/>
			<span v-if="query" class="absolute right-2 top-1/2 -translate-y-1/2 text-xs tabular-nums text-ink-gray-5" aria-live="polite">
				{{ total ? `${current + 1} / ${total}` : "0" }}
			</span>
		</div>
		<template v-if="total > 1">
			<button type="button" class="flex h-7 w-6 items-center justify-center rounded text-ink-gray-5 hover:bg-surface-gray-2" aria-label="Previous match" @click="step(-1)">
				<FeatherIcon name="chevron-up" class="h-4 w-4" />
			</button>
			<button type="button" class="flex h-7 w-6 items-center justify-center rounded text-ink-gray-5 hover:bg-surface-gray-2" aria-label="Next match" @click="step(1)">
				<FeatherIcon name="chevron-down" class="h-4 w-4" />
			</button>
		</template>
	</div>
</template>

<script setup>
// Find-in-page for a cockpit (#1592): searches the visible text of the page in #cockpit-main,
// highlights every match and steps through them. New content (infinite scroll, realtime
// updates) is searched as it arrives.
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { useRoute } from "vue-router"
import { findMatches, stepIndex } from "@spa/utils/textSearch.js"

const ROOT_ID = "cockpit-main"
const ALL = "cockpit-search"
const CURRENT = "cockpit-search-current"
const SKIP = new Set(["SCRIPT", "STYLE", "TEXTAREA", "INPUT", "SELECT", "NOSCRIPT"])

const route = useRoute()
const input = ref(null)
const query = ref("")
const total = ref(0)
const current = ref(-1)
let ranges = []
let observer = null
let rerunTimer = null
const supported = typeof CSS !== "undefined" && "highlights" in CSS

function textNodes(root) {
	const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
		acceptNode(node) {
			const parent = node.parentElement
			if (!parent || !node.nodeValue.trim()) return NodeFilter.FILTER_REJECT
			if (SKIP.has(parent.tagName) || parent.closest("[aria-hidden='true'], [hidden]")) return NodeFilter.FILTER_REJECT
			if (!parent.offsetParent && getComputedStyle(parent).position !== "fixed") return NodeFilter.FILTER_REJECT
			return NodeFilter.FILTER_ACCEPT
		},
	})
	const nodes = []
	while (walker.nextNode()) nodes.push(walker.currentNode)
	return nodes
}

function paint() {
	if (!supported) return
	CSS.highlights.delete(ALL)
	CSS.highlights.delete(CURRENT)
	if (!ranges.length) return
	CSS.highlights.set(ALL, new Highlight(...ranges))
	if (current.value >= 0) CSS.highlights.set(CURRENT, new Highlight(ranges[current.value]))
}

function run({ keep = false } = {}) {
	const root = document.getElementById(ROOT_ID)
	const needle = query.value.trim()
	ranges = []
	if (root && needle) {
		for (const node of textNodes(root)) {
			for (const start of findMatches(node.nodeValue, needle)) {
				const range = document.createRange()
				range.setStart(node, start)
				range.setEnd(node, start + needle.length)
				ranges.push(range)
			}
		}
	}
	total.value = ranges.length
	if (!keep) current.value = ranges.length ? 0 : -1
	else current.value = Math.min(current.value, ranges.length - 1)
	paint()
	if (!keep) reveal()
}

function reveal() {
	const range = ranges[current.value]
	if (!range) return
	range.startContainer.parentElement?.scrollIntoView({ block: "center", behavior: "smooth" })
	if (!supported) {
		const selection = window.getSelection()
		selection.removeAllRanges()
		selection.addRange(range)
	}
}

function step(direction) {
	if (!ranges.length) return run()
	current.value = stepIndex(current.value, ranges.length, direction)
	paint()
	reveal()
}

function clear() {
	query.value = ""
	input.value?.blur()
}

function scheduleRerun() {
	if (!query.value.trim()) return
	clearTimeout(rerunTimer)
	rerunTimer = setTimeout(() => run({ keep: true }), 300)
}

function onKeydown(event) {
	if (event.key !== "/" || event.ctrlKey || event.metaKey || event.altKey) return
	const target = event.target
	if (["INPUT", "TEXTAREA", "SELECT"].includes(target?.tagName) || target?.isContentEditable) return
	event.preventDefault()
	input.value?.focus()
	input.value?.select()
}

let typingTimer = null
watch(query, () => {
	clearTimeout(typingTimer)
	typingTimer = setTimeout(() => run(), 150)
})
watch(
	() => route.fullPath,
	async () => {
		await nextTick()
		setTimeout(() => run({ keep: false }), 400) // let the new page render
	}
)

onMounted(() => {
	window.addEventListener("keydown", onKeydown)
	const root = document.getElementById(ROOT_ID)
	if (root && typeof MutationObserver !== "undefined") {
		observer = new MutationObserver(scheduleRerun)
		observer.observe(root, { childList: true, subtree: true, characterData: true })
	}
})
onBeforeUnmount(() => {
	window.removeEventListener("keydown", onKeydown)
	observer?.disconnect()
	clearTimeout(rerunTimer)
	clearTimeout(typingTimer)
	if (supported) {
		CSS.highlights.delete(ALL)
		CSS.highlights.delete(CURRENT)
	}
})
</script>

<style>
/* The counter sits where the browser draws its clear button; Esc clears instead. */
input[aria-label="Search this page"]::-webkit-search-cancel-button {
	display: none;
}
::highlight(cockpit-search) {
	background-color: rgb(250 204 21 / 0.35);
}
::highlight(cockpit-search-current) {
	background-color: rgb(249 115 22 / 0.75);
	color: inherit;
}
</style>
