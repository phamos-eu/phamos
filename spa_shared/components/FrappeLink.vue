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
			<template v-if="stackDescription" #item-suffix="{ option }">
				<div
					v-if="option?.description"
					class="max-w-[55%] whitespace-normal text-right text-xs leading-snug text-ink-gray-5"
				>
					{{ option.description }}
				</div>
			</template>
		</Autocomplete>
	</div>
</template>

<script setup>
import { createResource, Autocomplete, debounce } from "frappe-ui"
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
	/** Show search_link description as a second line under the label in the dropdown. */
	stackDescription: {
		type: Boolean,
		default: false,
	},
})

const emit = defineEmits(["update:modelValue"])

const autocompleteRef = ref(null)
const wrapperEl = ref(null)
const searchText = ref("")

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
			if (doc.label) {
				return {
					label: doc.label,
					value: doc.value,
					description: doc.description || "",
				}
			}
			let title = null
			if (doc.description) {
				title = doc.description.split(",")[0]
			}
			return {
				label: title ? `${title} : ${doc.value}` : doc.value,
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
</script>
