<template>
	<!--
		Department-agnostic "Today" dashboard: it renders whatever sections the
		cockpit's own `get_today` returns, so each cockpit decides what matters
		today without needing its own view. Section shape:
		  { key, title, empty, items: [{ title, subtitle, meta, tone, route|url }] }
	-->
	<div class="min-h-0 flex-1 overflow-y-auto bg-surface-gray-1 p-5">
		<div class="mx-auto flex max-w-7xl flex-col gap-5">
			<div v-if="error" class="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
				{{ error }}
			</div>
			<div v-else-if="loading" class="flex min-h-64 items-center justify-center text-sm text-ink-gray-5">
				Loading…
			</div>
			<template v-else>
				<section class="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
					<div
						v-for="section in sections"
						:key="`count-${section.key}`"
						class="rounded-lg border border-outline-gray-2 bg-surface-white p-4"
					>
						<div class="text-xs font-medium uppercase tracking-wide text-ink-gray-5">
							{{ section.title }}
						</div>
						<div class="mt-2 text-2xl font-semibold tabular-nums text-ink-gray-9">
							{{ section.items.length }}
						</div>
					</div>
				</section>

				<section
					v-for="section in sections"
					:key="section.key"
					class="rounded-lg border border-outline-gray-2 bg-surface-white p-5"
				>
					<h2 class="mb-3 text-base font-semibold text-ink-gray-9">{{ section.title }}</h2>
					<p v-if="!section.items.length" class="text-sm text-ink-gray-5">{{ section.empty }}</p>
					<div v-else class="divide-y divide-outline-gray-1">
						<component
							:is="item.route ? 'button' : 'a'"
							v-for="(item, index) in section.items"
							:key="`${section.key}-${index}`"
							:href="item.route ? undefined : item.url"
							:type="item.route ? 'button' : undefined"
							class="flex w-full items-center gap-3 py-2 text-left hover:bg-surface-gray-2"
							@click="item.route ? router.push(item.route) : null"
						>
							<span class="h-2 w-2 flex-none rounded-full" :class="toneClass(item.tone)" />
							<span class="min-w-0 flex-1">
								<span class="block truncate text-sm font-medium text-ink-gray-9">{{ item.title }}</span>
								<span v-if="item.subtitle" class="block truncate text-xs text-ink-gray-6">
									{{ item.subtitle }}
								</span>
							</span>
							<span v-if="item.meta" class="flex-none text-xs text-ink-gray-6">{{ item.meta }}</span>
						</component>
					</div>
				</section>
			</template>
		</div>
	</div>
</template>

<script setup>
import { onMounted, ref } from "vue"
import { useRouter } from "vue-router"
import { call } from "frappe-ui"

const props = defineProps({
	/** Whitelisted method returning { sections: [...] } */
	method: { type: String, required: true },
})

const router = useRouter()

const loading = ref(true)
const error = ref("")
const sections = ref([])

const TONE_CLASSES = {
	red: "bg-red-500",
	amber: "bg-amber-500",
	blue: "bg-blue-500",
	green: "bg-green-500",
	gray: "bg-surface-gray-4",
}

function toneClass(tone) {
	return TONE_CLASSES[tone] || TONE_CLASSES.gray
}

onMounted(async () => {
	try {
		const data = await call(props.method)
		sections.value = data.sections || []
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not load today's dashboard"
	} finally {
		loading.value = false
	}
})
</script>
