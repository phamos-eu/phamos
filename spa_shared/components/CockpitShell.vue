<template>
	<div class="flex h-full min-h-0 bg-surface-gray-1 text-ink-gray-9">
		<slot name="sidebar" />
		<div class="flex min-w-0 flex-1 flex-col">
			<header
				class="flex h-12 flex-shrink-0 items-center border-b border-outline-gray-2 bg-surface-gray-1 px-5"
			>
				<div class="min-w-0 flex-1">
					<div id="cockpit-page-chrome" class="min-w-0" />
					<template v-if="!pageChrome.active">
						<div class="truncate text-base font-semibold tracking-tight text-ink-gray-9">
							{{ title }}
						</div>
					</template>
				</div>
				<div v-if="$slots['header-actions']" class="ml-auto flex flex-shrink-0 items-center gap-2 pl-3">
					<slot name="header-actions" />
				</div>
			</header>
			<main id="cockpit-main" class="min-h-0 flex-1 overflow-hidden bg-surface-gray-1">
				<router-view />
			</main>
		</div>
		<!-- One toast host for the whole cockpit; without it frappe-ui toast() calls show nothing. -->
		<Toasts />
		<!-- How to install this cockpit as a desktop app, on the first visits (#1998). -->
		<InstallAppDialog />
		<!-- The cockpit colour glowing in from the chosen window edges (#1933); never catches clicks. -->
		<div v-if="glow" aria-hidden="true" class="cockpit-glow" :style="glow.style">
			<div
				v-if="glow.steady"
				class="cockpit-glow__layer cockpit-glow__layer--steady"
				:class="{ 'is-breathing': glow.breathing }"
			>
				<span v-for="edge in glow.edges" :key="edge" :class="`cockpit-glow__edge cockpit-glow__edge--${edge}`">
					<i class="cockpit-glow__wave"><i class="cockpit-glow__wave-b" /></i>
				</span>
				<span v-for="corner in glow.corners" :key="corner" :class="`cockpit-glow__corner cockpit-glow__corner--${corner}`" />
			</div>
			<div
				v-if="glow.pulse"
				class="cockpit-glow__layer cockpit-glow__layer--pulse"
				:class="{ 'is-on': glow.pulsing.value }"
			>
				<span v-for="edge in glow.frame.edges" :key="edge" :class="`cockpit-glow__edge cockpit-glow__edge--${edge}`">
					<i class="cockpit-glow__wave"><i class="cockpit-glow__wave-b" /></i>
				</span>
				<span
					v-for="corner in glow.frame.corners"
					:key="corner"
					:class="`cockpit-glow__corner cockpit-glow__corner--${corner}`"
				/>
			</div>
		</div>
	</div>
</template>

<script setup>
import { onBeforeUnmount, onMounted } from "vue"
import { useRouter } from "vue-router"
import { Toasts } from "frappe-ui"
import { pageChrome } from "@spa/pageChrome.js"
import InstallAppDialog from "@spa/components/InstallAppDialog.vue"
import { mountPhriend } from "@spa/phriend.js"
import { useCockpitGlow } from "@spa/composables/useCockpitGlow.js"
import { onDialogSaveKey } from "@spa/utils/shortcuts.js"

const props = defineProps({
	title: { type: String, default: "" },
	subtitle: { type: String, default: "" },
})

// Phriend, the report-a-problem ball, in every cockpit (#1900). The page title the shell shows
// becomes part of "Reported on"; on record pages the record itself is named instead.
const router = useRouter()
const glow = useCockpitGlow()
onMounted(() => mountPhriend(router, () => props.title))

// Ctrl/Cmd+S runs the open dialog's primary action, as in Frappe Desk (#2032).
const onSaveKey = (event) => onDialogSaveKey(event)
onMounted(() => document.addEventListener("keydown", onSaveKey, true))
onBeforeUnmount(() => document.removeEventListener("keydown", onSaveKey, true))
</script>
