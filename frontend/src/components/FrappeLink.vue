<template>
	<Autocomplete
		ref="autocompleteRef"
		size="sm"
		v-model="value"
		:placeholder="placeholder"
		:options="options.data || []"
		:class="disabled ? 'pointer-events-none opacity-60' : ''"
		:disabled="disabled"
		@update:query="handleQueryUpdate"
	/>
</template>

<script setup>
import { createResource, Autocomplete, debounce } from "frappe-ui"
import { ref, computed, watch } from "vue"

const props = defineProps({
	doctype: {
		type: String,
		required: true,
	},
	modelValue: {
		type: String,
		default: "",
	},
	filters: {
		type: Object,
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
const searchText = ref("")

const value = computed({
	get: () => props.modelValue,
	set: (val) => {
		const newVal =
			val && typeof val === "object" && val.value !== undefined ? val.value : val
		emit("update:modelValue", newVal || "")
	},
})

const options = createResource({
	url: "frappe.desk.search.search_link",
	params: {
		doctype: props.doctype,
		txt: searchText.value,
		filters: props.filters,
	},
	method: "POST",
	transform: (data) => {
		const mapped = (data || []).map((doc) => {
			let title = null
			if (doc.label && doc.label !== doc.value) {
				title = doc.label
			} else if (doc.description) {
				title = doc.description.split(",")[0]
			}
			return {
				label: title ? `${title} : ${doc.value}` : doc.value,
				value: doc.value,
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
