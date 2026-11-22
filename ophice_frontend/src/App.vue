<template>
	<!--
		Ophice (#2070, #2073): the map is always loaded; a cockpit opens over it in a frame and
		stays loaded when I go back to the map, so I return to where I was.
	-->
	<!-- Guests (#2082): their own page, nothing of the employees' Ophice is loaded. -->
	<div v-if="isGuest" class="h-full min-h-0">
		<GuestView />
		<Toasts />
	</div>
	<div v-else class="relative h-full min-h-0">
		<Ophice
			:cockpit-open="frameVisible"
			:open-route="openRoute"
			@open-cockpit="openCockpit"
			@back-to-map="router.push({ name: 'Map' })"
		/>
		<CockpitFrame
			v-if="frameSrc"
			v-show="frameVisible"
			:src="frameSrc"
			:frame-key="frameKey"
			@navigated="onNavigated"
			@back="router.push({ name: 'Map' })"
			@leave="onLeave"
		/>
		<router-view />
		<Toasts />
	</div>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { Toasts } from "frappe-ui"
import Ophice from "./views/Ophice.vue"
import CockpitFrame from "./components/CockpitFrame.vue"
import { isOwnPage } from "./utils/ophicePage.js"
import GuestView from "./views/GuestView.vue"

// Decided before anything loads: a guest page must never call the employees' API.
const isGuest = globalThis.location.pathname.replace(/\/$/, "") === "/ophice/guest"
const route = useRoute()
const router = useRouter()
const window = globalThis.window

const frameSrc = ref("")
const frameKey = ref(0)
// Where the frame is now (its own navigation), e.g. "/sales-cockpit/leads".
const frameAt = ref("")
const frameVisible = computed(() => route.name === "Cockpit")
// The cockpit's base route, e.g. "/sales-cockpit": the first segment of where the frame is.
const openRoute = computed(() => (frameAt.value ? `/${frameAt.value.split(/[/?#]/)[1] || ""}` : ""))

/** "/personal-cockpit/todos" from the route /open/personal-cockpit/todos, with its query. */
function pageOf(to) {
	const path = [].concat(to.params.path || []).join("/")
	const query = new URLSearchParams(to.query).toString()
	return `/${path}${query ? `?${query}` : ""}${to.hash || ""}`
}

function load(page) {
	if (!isOwnPage(page)) {
		router.replace({ name: "Map" })
		return
	}
	frameAt.value = page
	frameSrc.value = page
	frameKey.value += 1
}

// The address decides: /open/... shows that cockpit page (loading it if the frame is elsewhere),
// "/" shows the map and keeps the frame as it is.
watch(
	() => route.fullPath,
	() => {
		if (route.name !== "Cockpit") return
		const page = pageOf(route)
		if (page !== frameAt.value) load(page)
	},
	{ immediate: true }
)

/** From the shortcut bar: show the cockpit; if it is the one already open, where I left it. */
function openCockpit(cockpit) {
	const page = openRoute.value === cockpit.route ? frameAt.value : cockpit.route
	router.push(`/open${page}`)
}

/**
 * The frame went somewhere that belongs in the whole window. Ophice itself: back to the map, and
 * the frame back to the last cockpit page (no Ophice inside Ophice). Anything else (the login
 * page): the whole window goes there.
 */
function onLeave(url) {
	if (url.startsWith("/ophice")) {
		const page = frameAt.value
		router.push({ name: "Map" })
		if (page) load(page)
		else frameSrc.value = ""
		return
	}
	window.location.assign(url)
}

/** The cockpit moved on by itself: keep Ophice's address in step, without reloading anything. */
function onNavigated(page) {
	frameAt.value = page
	if (route.name === "Cockpit" && pageOf(route) !== page) router.replace(`/open${page}`)
}
</script>
