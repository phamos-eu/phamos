<template>
	<Autocomplete
		ref="autocompleteRef"
		size="sm"
		v-model="value"
		:placeholder="placeholder"
		:options="options"
		:disabled="disabled"
		body-classes="checklist-template-picker w-[min(100%,42rem)] min-w-[20rem]"
		@update:query="handleQueryUpdate"
	>
		<template #target="{ togglePopover }">
			<div class="w-full">
				<button
					type="button"
					class="flex min-h-7 w-full items-center justify-between gap-2 rounded border border-transparent bg-surface-gray-2 px-2 py-1 text-left transition-colors hover:bg-surface-gray-3 focus:border-outline-gray-4 focus:outline-none focus:ring-2 focus:ring-outline-gray-3 disabled:cursor-not-allowed disabled:opacity-60"
					:disabled="disabled"
					@click="togglePopover"
				>
					<span
						class="min-w-0 flex-1 break-words text-base leading-5 whitespace-normal"
						:class="selectedTitle ? 'text-ink-gray-8' : 'text-ink-gray-4'"
					>
						{{ selectedTitle || placeholder }}
					</span>
					<FeatherIcon name="chevron-down" class="h-4 w-4 shrink-0 text-ink-gray-5" />
				</button>
			</div>
		</template>

		<template #item-prefix="{ option }">
			<div class="min-w-0 w-full space-y-1.5 py-0.5">
				<div
					class="break-words font-medium leading-snug text-ink-gray-8 whitespace-normal"
				>
					{{ option.title || option.value }}
				</div>
				<ul
					v-if="option.preview_lines?.length"
					class="space-y-0.5 text-xs leading-snug text-ink-gray-5"
				>
					<li v-for="(line, idx) in option.preview_lines" :key="idx">
						<span class="text-ink-gray-6">{{ line.label }}:</span>
						{{ line.value }}
					</li>
				</ul>
			</div>
		</template>
	</Autocomplete>
</template>

<script setup>
import { Autocomplete, call, debounce, FeatherIcon } from "frappe-ui"
import { computed, ref, watch } from "vue"

const props = defineProps({
	modelValue: { type: String, default: "" },
	document: { type: String, required: true },
	disabled: { type: Boolean, default: false },
	placeholder: { type: String, default: "Optional — pick a template" },
})

const emit = defineEmits(["update:modelValue"])

const API = "phamos.api.checklist_inbox"

const autocompleteRef = ref(null)
const options = ref([])
const searchText = ref("")

const value = computed({
	get: () => props.modelValue,
	set: (val) => {
		const newVal =
			val && typeof val === "object" && val.value !== undefined ? val.value : val
		emit("update:modelValue", newVal || "")
	},
})

const selectedTitle = computed(() => {
	if (!props.modelValue) return ""
	const match = options.value.find((o) => o.value === props.modelValue)
	return match?.title || props.modelValue
})

function mapOptions(rows) {
	const mapped = (rows || []).map((row) => ({
		// Kept for Autocomplete client-side filter; default label span is hidden via CSS.
		label: row.title || row.value,
		value: row.value,
		title: row.title || row.value,
		preview_lines: row.preview_lines || [],
	}))
	if (props.modelValue && !mapped.find((o) => o.value === props.modelValue)) {
		mapped.unshift({
			label: props.modelValue,
			value: props.modelValue,
			title: props.modelValue,
			preview_lines: [],
		})
	}
	return mapped
}

async function loadOptions(txt = "") {
	if (!props.document) {
		options.value = []
		return
	}
	const rows = await call(`${API}.get_checklist_template_picker_options`, {
		document: props.document,
		txt,
	})
	options.value = mapOptions(rows)
}

const handleQueryUpdate = debounce((newQuery) => {
	const val = newQuery || ""
	if (val === "" && props.modelValue) return
	if (searchText.value === val) return
	searchText.value = val
	loadOptions(val)
}, 300)

watch(
	() => props.document,
	() => loadOptions(searchText.value),
	{ immediate: true }
)

watch(
	() => props.modelValue,
	(newVal, oldVal) => {
		if (!newVal && oldVal) {
			searchText.value = ""
			loadOptions("")
		} else if (newVal && newVal !== oldVal) {
			const inOptions = options.value.find((o) => o.value === newVal)
			if (!inOptions) loadOptions("")
		}
	}
)
</script>

<!--
  Unscoped: Autocomplete options live under bodyClasses on the popover panel,
  not under the host root — scoped/host selectors never matched.
-->
<style>
.checklist-template-picker li.flex.cursor-pointer {
	align-items: flex-start !important;
	padding-top: 0.625rem;
	padding-bottom: 0.625rem;
}

.checklist-template-picker li.flex.cursor-pointer > div.flex.flex-1 {
	align-items: flex-start !important;
	overflow: visible !important;
	width: 100%;
}

/* Prefix holds the full stacked content; grow instead of shrink-0. */
.checklist-template-picker li.flex.cursor-pointer > div.flex.flex-1 > div.flex.flex-shrink-0 {
	flex: 1 1 auto !important;
	min-width: 0;
	width: 100%;
}

/* Hide Autocomplete's default label (duplicate title). */
.checklist-template-picker li.flex.cursor-pointer > div.flex.flex-1 > span {
	display: none !important;
}

.checklist-template-picker li.flex.cursor-pointer > div.ml-2 {
	display: none !important;
}
</style>
