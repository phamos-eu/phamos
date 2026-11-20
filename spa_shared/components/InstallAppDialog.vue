<template>
	<!-- How to install this cockpit as its own desktop app (#1998). Opens by itself on the first
	     visits (see utils/installHint.js) and from the sidebar's "Install as app". -->
	<Dialog :options="{ title: __('Use {0} as an app', [appName]), size: 'lg', actions }" v-model="installApp.open">
		<template #body-content>
			<div class="flex gap-4 text-sm text-ink-gray-8">
				<img v-if="icon" :src="icon" alt="" class="h-14 w-14 flex-shrink-0 rounded-xl" />
				<div class="flex min-w-0 flex-col gap-3">
					<p>{{ __("Install it once and it opens in its own window, from the Dock or taskbar, without searching for a browser tab.") }}</p>

					<p v-if="installApp.prompt" class="text-ink-gray-7">{{ __("Your browser can do it with one click.") }}</p>
					<template v-else>
						<ol v-if="steps.length" class="flex list-decimal flex-col gap-1 pl-5">
							<li v-for="(step, index) in steps" :key="index">{{ step }}</li>
						</ol>
						<p v-if="note" class="text-ink-gray-6">{{ note }}</p>
					</template>
				</div>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { Dialog } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"
import { canOfferInstall, installApp } from "@spa/installApp.js"
import { browserFamily, readState, shouldShowHint, storageKey, writeState } from "@spa/utils/installHint.js"

// Give the page a moment to appear before anything pops up over it.
const SHOW_DELAY_MS = 1500

const appName = ref(document.title || __("this cockpit"))
const icon = ref("")
// The manifest id replaces this; the cockpit's route ("/team-cockpit") is the same value.
const key = ref(storageKey(`/${location.pathname.split("/")[1] || ""}`))
// Opened by the page itself (counts towards MAX_SHOWS) or from the sidebar (doesn't).
const automatic = ref(false)
let timer = null

const family = browserFamily(navigator.userAgent, navigator.userAgentData?.brands)

const steps = computed(() => {
	if (family === "chrome")
		return [
			__("Click the install icon at the right end of the address bar, or open the ⋮ menu."),
			__("Choose “Cast, save and share” → “Install page as app”."),
		]
	if (family === "edge")
		return [
			__("Click the install icon at the right end of the address bar, or open the … menu."),
			__("Choose “Apps” → “Install this site as an app”."),
		]
	if (family === "safari") return [__("Choose File → Add to Dock in the menu bar."), __("Confirm with “Add”.")]
	return []
})

const note = computed(() => {
	if (family === "firefox")
		return __("Firefox can't install web apps. Open the cockpit in Chrome, Edge or Safari to install it.")
	if (family === "other") return __("Look for “Install” or “Add to Dock” in your browser's menu.")
	if (family === "chrome" || family === "edge")
		return __("If the entry is missing, the app may already be installed: look for it in your apps.")
	return ""
})

const actions = computed(() => {
	const list = []
	if (installApp.prompt) list.push({ label: __("Install"), variant: "solid", onClick: install })
	if (automatic.value) {
		list.push({ label: __("Later"), variant: installApp.prompt ? "subtle" : "solid", onClick: close })
		list.push({ label: __("Don't show again"), variant: "ghost", onClick: () => remember(true) })
	} else {
		list.push({ label: __("Close"), variant: installApp.prompt ? "subtle" : "solid", onClick: close })
	}
	return list
})

// Reading window.localStorage itself throws when the browser blocks storage.
function storage() {
	try {
		return window.localStorage
	} catch (e) {
		return null
	}
}

function close() {
	installApp.open = false
}

/** Never again in this browser: after "Don't show again", or once installed. */
function remember(dismissed) {
	const state = readState(storage(), key.value)
	writeState(storage(), key.value, { ...state, dismissed })
	close()
}

async function install() {
	const event = installApp.prompt
	if (!event) return
	event.prompt()
	const choice = await event.userChoice.catch(() => null)
	// The event works once only, whatever the user chose.
	installApp.prompt = null
	if (choice?.outcome === "accepted") remember(true)
}

// Each cockpit names its own app in its manifest; read name, id and icon from there.
async function loadManifest() {
	const href = document.querySelector('link[rel="manifest"]')?.href
	if (!href) return
	try {
		const manifest = await (await fetch(href, { credentials: "same-origin" })).json()
		if (manifest.name) appName.value = manifest.name
		// Relative paths in a manifest resolve against the manifest's URL, not the page's.
		if (manifest.id) key.value = storageKey(new URL(manifest.id, href).pathname)
		const best = (manifest.icons || []).find((i) => i.sizes === "192x192" && i.purpose !== "maskable")
		const src = (best || manifest.icons?.[0])?.src
		icon.value = src ? new URL(src, href).href : ""
	} catch (e) {
		/* the hint still works with the page title */
	}
}

watch(
	() => installApp.installed,
	(installed) => installed && remember(true)
)

onMounted(async () => {
	await loadManifest()
	const state = readState(storage(), key.value)
	if (!shouldShowHint({ installed: !canOfferInstall(), width: window.innerWidth, state, family })) return
	timer = setTimeout(() => {
		// Once per page load at most, even if the shell were ever mounted again.
		if (installApp.open || installApp.autoShown) return
		installApp.autoShown = true
		automatic.value = true
		installApp.open = true
		writeState(storage(), key.value, { ...state, shown: state.shown + 1 })
	}, SHOW_DELAY_MS)
})
onBeforeUnmount(() => clearTimeout(timer))

// From the sidebar: the same dialog without "Later" and "Don't show again".
watch(
	() => installApp.open,
	(open) => {
		if (!open) automatic.value = false
	}
)
</script>
