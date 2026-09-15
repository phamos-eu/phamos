<template>
	<div ref="wrapperEl" @keydown="onTriggerKeydown">
		<Autocomplete
			ref="autocompleteRef"
			size="sm"
			v-model="value"
			:placeholder="placeholder"
			:options="options.data || []"
			:class="disabled ? 'pointer-events-none opacity-60' : ''"
			:disabled="disabled"
			@update:query="handleQueryUpdate"
		>
			<template #item-suffix="{ option }">
				<div
					v-if="previewLines[option.value]?.length"
					class="max-w-[60%] space-y-0.5 whitespace-normal text-right text-xs leading-snug text-ink-gray-5"
				>
					<div v-for="line in previewLines[option.value]" :key="line.label">
						<span class="text-ink-gray-6">{{ line.label }}:</span> {{ line.value }}
					</div>
				</div>
			</template>
		</Autocomplete>
	</div>
</template>

<script setup>
import { createResource, Autocomplete, call, debounce } from "frappe-ui"
import { ref, computed, watch, nextTick } from "vue"

const props = defineProps({
	doctype: {
		type: String,
		required: true,
	},
	modelValue: {
		type: String,
		default: "",
	},
	query: {
		type: String,
		default: "",
	},
	filters: {
		type: [Object, Array],
		default: () => ({}),
	},
	disabled: {
		type: Boolean,
		default: false,
	},
	placeholder: {
		type: String,
		default: "",
	},
})

const emit = defineEmits(["update:modelValue"])

const autocompleteRef = ref(null)
const wrapperEl = ref(null)
const searchText = ref("")
// { [value]: [{label, value}] } — labelled Search Fields + "Show in Preview"
// fields for the options currently listed, so users can tell records apart.
const previewLines = ref({})

// Autocomplete's closed trigger is a plain <button> that only opens on click;
// once open, focus moves to its own search input, which headlessui already
// drives with the arrow keys. So only intercept the keys while still closed.
function onTriggerKeydown(event) {
	if (props.disabled) return
	if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return
	if (event.target?.tagName !== "BUTTON") return
	event.preventDefault()
	autocompleteRef.value?.togglePopover?.()
}

const value = computed({
	get: () => props.modelValue,
	set: (val) => {
		const newVal =
			val && typeof val === "object" && val.value !== undefined ? val.value : val
		emit("update:modelValue", newVal || "")
		// Selecting (or clearing) an option hides the dropdown via display:none,
		// which per spec blurs focus to <body> — restore it to our own trigger
		// button so a following Tab continues to the next field, not the top of
		// the whole page.
		nextTick(() => wrapperEl.value?.querySelector("button")?.focus())
	},
})

const options = createResource({
	url: "frappe.desk.search.search_link",
	params: {
		doctype: props.doctype,
		txt: searchText.value,
		filters: props.filters,
		...(props.query ? { query: props.query } : {}),
	},
	method: "POST",
	transform: (data) => {
		const mapped = (data || []).map((doc) => {
			// search_link joins matched fields with ", " into `description`. Without
			// a title_field it doesn't include the record's own name, so keep
			// showing "<first field> : <name>" as this field always has, and fold
			// any remaining search-field values in as `extra`.
			const descriptionParts = doc.description ? doc.description.split(", ") : []
			const title =
				doc.label || (descriptionParts.length ? `${descriptionParts[0]} : ${doc.value}` : doc.value)
			const extra = doc.label ? descriptionParts : descriptionParts.slice(1)
			// search_link already matches txt against the doctype's configured
			// Search Fields server-side (the values making up `extra` here) —
			// but Autocomplete re-filters its options client-side by label/value
			// only, so a record the server correctly matched via e.g. an email
			// Search Field would otherwise get silently dropped again here.
			// Folding that text into the label keeps it searchable.
			const label = extra.length ? `${title} — ${extra.join(", ")}` : title
			return {
				label,
				value: doc.value,
				description: doc.description || "",
			}
		})

		if (props.modelValue && !mapped.find((o) => o.value === props.modelValue)) {
			mapped.unshift({ label: props.modelValue, value: props.modelValue })
		}
		return mapped
	},
})

const reloadOptions = (searchTextVal) => {
	if (!props.doctype) {
		options.reset()
		return
	}
	options.update({
		params: {
			txt: searchTextVal,
			doctype: props.doctype,
			filters: props.filters,
			...(props.query ? { query: props.query } : {}),
		},
	})
	options.reload()
}

const handleQueryUpdate = debounce((newQuery) => {
	const val = newQuery || ""
	if (val === "" && props.modelValue) return
	if (searchText.value === val) return
	searchText.value = val
	reloadOptions(val)
}, 300)

watch(
	() => props.doctype,
	() => {
		if (!props.doctype) return
		reloadOptions(props.modelValue)
	},
	{ immediate: true }
)

watch(
	() => props.filters,
	() => reloadOptions(""),
	{ deep: true }
)

watch(
	() => props.modelValue,
	(newVal, oldVal) => {
		if (!newVal && oldVal) {
			searchText.value = ""
			reloadOptions("")
		} else if (newVal && newVal !== oldVal) {
			const inOptions = (options.data || []).find((o) => o.value === newVal)
			if (options.data && !inOptions) reloadOptions("")
		}
	}
)

let previewToken = 0

watch(
	() => options.data,
	async (data) => {
		const token = ++previewToken
		const names = (data || []).map((option) => option.value).filter(Boolean)
		if (!props.doctype || !names.length) {
			previewLines.value = {}
			return
		}
		try {
			const lines = await call("phamos.api.link_preview.get_link_preview_lines", {
				doctype: props.doctype,
				names,
			})
			if (token === previewToken) previewLines.value = lines || {}
		} catch (e) {
			if (token === previewToken) previewLines.value = {}
		}
	}
)
</script>
