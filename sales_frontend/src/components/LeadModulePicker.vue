<template>
	<!-- Mirrors AssigneePicker: chips for what's chosen, one-click suggestions,
	     and a search field for everything else. -->
	<div>
		<div class="mb-1.5 flex items-center justify-between gap-2">
			<label class="text-xs text-ink-gray-5">Modules</label>
			<span v-if="modelValue.length" class="text-xs text-ink-gray-6">{{ modelValue.length }}</span>
		</div>

		<div v-if="modelValue.length" class="mb-1.5 flex flex-wrap gap-1.5">
			<span
				v-for="row in modelValue"
				:key="row.module"
				class="inline-flex items-center gap-1 rounded-full bg-surface-gray-3 py-0.5 pl-2 pr-1 text-xs font-medium text-ink-gray-9"
			>
				<span>{{ row.module_name || row.module }}</span>
				<button
					type="button"
					class="rounded-full p-0.5 text-ink-gray-6 hover:bg-surface-gray-4 hover:text-ink-gray-9"
					:title="`Remove ${row.module_name || row.module}`"
					@click="remove(row.module)"
				>
					<FeatherIcon name="x" class="h-3 w-3" />
				</button>
			</span>
		</div>
		<div v-else class="mb-1.5 text-xs text-ink-gray-5">No modules yet</div>

		<div v-if="availableSuggestions.length" class="mb-1.5 flex flex-wrap gap-1.5">
			<button
				v-for="suggestion in availableSuggestions"
				:key="suggestion.name"
				type="button"
				class="rounded-full border border-dashed border-outline-gray-3 px-2 py-0.5 text-xs text-ink-gray-8 hover:border-outline-gray-4 hover:bg-surface-gray-2"
				@click="add(suggestion.name, suggestion.module_name)"
			>
				+ {{ suggestion.module_name }}
			</button>
		</div>

		<FrappeLink
			doctype="Implementation Module"
			:model-value="''"
			placeholder="Search modules…"
			@update:model-value="onSearchSelect"
		/>
	</div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue"
import { call } from "frappe-ui"
import FrappeLink from "@spa/components/FrappeLink.vue"

const props = defineProps({
	/** [{ module, module_name }] */
	modelValue: { type: Array, default: () => [] },
})

const emit = defineEmits(["update:modelValue"])

const suggestions = ref([])

/** Don't suggest what's already on the lead. */
const availableSuggestions = computed(() => {
	const chosen = new Set(props.modelValue.map((row) => row.module))
	return suggestions.value.filter((s) => !chosen.has(s.name))
})

function add(module, moduleName) {
	if (!module || props.modelValue.some((row) => row.module === module)) return
	emit("update:modelValue", [...props.modelValue, { module, module_name: moduleName || module }])
}

function remove(module) {
	emit(
		"update:modelValue",
		props.modelValue.filter((row) => row.module !== module)
	)
}

function onSearchSelect(value) {
	if (!value) return
	const known = suggestions.value.find((s) => s.name === value)
	add(value, known?.module_name)
}

onMounted(async () => {
	try {
		suggestions.value = await call("phamos.api.sales_leads.get_module_suggestions")
	} catch (e) {
		suggestions.value = []
	}
})
</script>
