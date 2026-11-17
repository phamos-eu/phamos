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
		<!-- The cockpit colour along the window edges (#1933); never catches clicks. -->
		<div
			v-if="glow"
			aria-hidden="true"
			class="cockpit-glow"
			:class="{ 'cockpit-glow--steady': glow.steady, 'cockpit-glow--pulse': glow.pulsing.value }"
			:style="{ '--cockpit-rgb': glow.rgb }"
		/>
	</div>
</template>

<script setup>
import { onMounted } from "vue"
import { useRouter } from "vue-router"
import { Toasts } from "frappe-ui"
import { pageChrome } from "@spa/pageChrome.js"
import { mountPhriend } from "@spa/phriend.js"
import { useCockpitGlow } from "@spa/composables/useCockpitGlow.js"

const props = defineProps({
	title: { type: String, default: "" },
	subtitle: { type: String, default: "" },
})

// Phriend, the report-a-problem ball, in every cockpit (#1900). The page title the shell shows
// becomes part of "Reported on"; on record pages the record itself is named instead.
const router = useRouter()
const glow = useCockpitGlow()
onMounted(() => mountPhriend(router, () => props.title))
</script>
