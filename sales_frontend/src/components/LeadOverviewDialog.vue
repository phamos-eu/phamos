<template>
	<!-- The detail behind one figure of the lead overview (#1758). Every row opens the leads it counts. -->
	<Dialog v-model="open" :options="{ title, size: '2xl' }">
		<template #body-content>
			<p v-if="intro" class="mb-4 text-sm text-ink-gray-6">{{ intro }}</p>
			<p v-if="!sections.some((s) => s.rows.length)" class="py-6 text-center text-sm text-ink-gray-5">
				{{ emptyText }}
			</p>
			<section v-for="section in sections" v-show="section.rows.length" :key="section.title" class="mb-5 last:mb-0">
				<h3 v-if="section.title" class="mb-2 text-xs font-medium uppercase tracking-wide text-ink-gray-5">
					{{ section.title }}
				</h3>
				<table class="w-full text-sm">
					<thead>
						<tr class="border-b border-outline-gray-2 text-xs text-ink-gray-5">
							<th
								v-for="column in section.columns"
								:key="column.key"
								class="py-1.5 font-medium"
								:class="column.numeric ? 'text-right tabular-nums' : 'text-left'"
							>
								{{ column.label }}
							</th>
						</tr>
					</thead>
					<tbody>
						<tr
							v-for="row in section.rows"
							:key="row.key"
							class="border-b border-outline-gray-1 last:border-0"
							:class="row.query ? 'cursor-pointer hover:bg-surface-gray-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-outline-gray-4' : ''"
							:tabindex="row.query ? 0 : undefined"
							:role="row.query ? 'link' : undefined"
							@click="row.query && go(row.query)"
							@keydown.enter.prevent="row.query && go(row.query)"
						>
							<td
								v-for="column in section.columns"
								:key="column.key"
								class="py-2"
								:class="[column.numeric ? 'text-right tabular-nums' : 'text-left', toneClass(row.tones?.[column.key])]"
							>
								<template v-if="column.links && row.links?.[column.key]">
									<button
										type="button"
										class="underline decoration-dotted underline-offset-2 hover:text-ink-gray-9"
										@click.stop="go(row.links[column.key])"
									>
										{{ row.cells[column.key] }}
									</button>
								</template>
								<template v-else>{{ row.cells[column.key] }}</template>
							</td>
						</tr>
					</tbody>
				</table>
			</section>
			<p v-if="note" class="mt-4 text-xs text-ink-gray-5">{{ note }}</p>
		</template>
	</Dialog>
</template>

<script setup>
import { computed } from "vue"
import { useRouter } from "vue-router"
import { Dialog } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"

const props = defineProps({
	modelValue: { type: Boolean, default: false },
	title: { type: String, default: "" },
	intro: { type: String, default: "" },
	note: { type: String, default: "" },
	emptyText: { type: String, default: () => __("No leads in this period.") },
	// [{ title, columns: [{ key, label, numeric?, links? }], rows: [{ key, cells, query?, links?, tones? }] }]
	sections: { type: Array, default: () => [] },
})

const emit = defineEmits(["update:modelValue"])
const router = useRouter()

const open = computed({
	get: () => props.modelValue,
	set: (value) => emit("update:modelValue", value),
})

function toneClass(tone) {
	if (tone === "above" || tone === "good") return "text-ink-green-3"
	if (tone === "below" || tone === "bad") return "text-ink-red-3"
	return ""
}

/** Open the lead list with a figure's filters. */
function go(query) {
	open.value = false
	router.push({ name: "LeadsFollowUps", query })
}
</script>
