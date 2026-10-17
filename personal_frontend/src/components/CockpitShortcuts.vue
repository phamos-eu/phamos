<template>
	<Dialog v-model="shortcuts.open" :options="{ title: 'Keyboard shortcuts', size: 'lg' }">
		<template #body-content>
			<div class="space-y-5">
				<section v-for="group in GROUPS" :key="group.title">
					<h3 class="mb-2 text-xs font-medium uppercase tracking-wide text-ink-gray-5">{{ group.title }}</h3>
					<dl class="divide-y divide-outline-gray-1">
						<div v-for="row in group.rows" :key="row.what" class="flex items-center justify-between gap-4 py-1.5 text-sm">
							<dt class="text-ink-gray-8">{{ row.what }}</dt>
							<dd class="flex flex-none items-center gap-1">
								<template v-for="(key, index) in row.keys" :key="key">
									<span v-if="index" class="text-xs text-ink-gray-4">or</span>
									<kbd class="rounded border border-outline-gray-2 bg-surface-gray-2 px-1.5 py-0.5 font-mono text-xs text-ink-gray-7">
										{{ key }}
									</kbd>
								</template>
							</dd>
						</div>
					</dl>
				</section>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
// Shortcuts of the Personal Cockpit (#1603): Ctrl/Cmd+B opens Create, j/k and the arrow keys move
// through lists, "?" opens this overview. Page-specific shortcuts stay with their pages and are
// only listed here, so there is one place to find them all.
import { onBeforeUnmount, onMounted } from "vue"
import { insideOverlay, isCreateKey, isPlainKey, isTypingTarget, listDirection, nextListIndex } from "@spa/utils/shortcuts.js"
import { shortcuts } from "@/shortcutsStore.js"

const emit = defineEmits(["create"])

const MOD = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform) ? "⌘" : "Ctrl"
const GROUPS = [
	{
		title: "Everywhere",
		rows: [
			{ what: "Create something new", keys: [`${MOD}+B`] },
			{ what: "Search this page", keys: ["/"] },
			{ what: "Next or previous match", keys: ["Enter", "Shift+Enter"] },
			{ what: "Move through a list", keys: ["j / k", "↓ / ↑"] },
			{ what: "Open the focused row", keys: ["Enter"] },
			{ what: "Revoke a fresh check-in or check-out", keys: [`${MOD}+Z`] },
			{ what: "Show these shortcuts", keys: ["?"] },
		],
	},
	{
		title: "My Day",
		rows: [{ what: "Jump to today", keys: ["T"] }],
	},
	{
		title: "Matrix",
		rows: [
			{ what: "Move the focused ToDo to quadrant 1–4", keys: ["1", "2", "3", "4"] },
			{ what: "Open the focused ToDo", keys: ["Enter"] },
		],
	},
	{
		title: "Dialogs",
		rows: [
			{ what: "Save or confirm", keys: [`${MOD}+Enter`] },
			{ what: "Close", keys: ["Esc"] },
		],
	},
]

// Rows of the visible list, in page order. Lists mark their rows with data-list-item.
function listRows() {
	const root = document.getElementById("cockpit-main")
	if (!root) return []
	return [...root.querySelectorAll("[data-list-item]")].filter((row) => row.offsetParent !== null)
}

function moveInList(direction) {
	const rows = listRows()
	if (!rows.length) return false
	const index = nextListIndex(rows.indexOf(document.activeElement), rows.length, direction)
	if (index < 0) return false
	rows[index].focus()
	rows[index].scrollIntoView({ block: "nearest" })
	return true
}

function onKeydown(event) {
	if (event.defaultPrevented) return
	const target = event.target
	if (isCreateKey(event)) {
		// Ctrl+B also works from a field: it never types a character.
		event.preventDefault()
		emit("create")
		return
	}
	if (isTypingTarget(target) || insideOverlay(target) || shortcuts.open) return
	if (event.key === "?" && isPlainKey(event)) {
		event.preventDefault()
		shortcuts.open = true
		return
	}
	const direction = listDirection(event, Boolean(target?.closest?.("[data-list-item]")))
	if (direction && moveInList(direction)) event.preventDefault()
}

onMounted(() => window.addEventListener("keydown", onKeydown))
onBeforeUnmount(() => window.removeEventListener("keydown", onKeydown))
</script>
