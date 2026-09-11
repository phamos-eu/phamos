<template>
	<div class="space-y-3">
		<div class="text-[11px] font-semibold uppercase tracking-wide text-ink-gray-6">
			Assignees
		</div>

		<div v-if="selected.length" class="flex flex-wrap gap-1.5">
			<span
				v-for="user in selected"
				:key="user.name"
				class="inline-flex items-center gap-1 rounded-full bg-surface-gray-3 py-0.5 pl-1 pr-1 text-xs font-medium text-ink-gray-9"
			>
				<UserAvatar
					size="sm"
					:name="user.name"
					:label="user.full_name || user.name"
					:image="user.user_image"
				/>
				<span class="pl-0.5">{{ user.full_name || user.name }}</span>
				<button
					type="button"
					class="rounded-full p-0.5 text-ink-gray-6 hover:bg-surface-gray-4 hover:text-ink-gray-9"
					:disabled="saving"
					:title="`Remove ${user.full_name || user.name}`"
					@click="removeUser(user.name)"
				>
					<FeatherIcon name="x" class="h-3 w-3" />
				</button>
			</span>
		</div>
		<div v-else class="text-sm text-ink-gray-6">No assignees</div>

		<div v-if="availableShortlist.length" class="space-y-1.5">
			<div class="text-[11px] font-medium text-ink-gray-6">Suggested</div>
			<div class="flex flex-wrap gap-1.5">
				<button
					v-for="user in availableShortlist"
					:key="user.name"
					type="button"
					class="inline-flex items-center gap-1.5 rounded-full border border-dashed border-outline-gray-3 py-0.5 pl-1 pr-2.5 text-xs text-ink-gray-8 hover:border-outline-gray-4 hover:bg-surface-gray-2"
					:disabled="saving"
					@click="addUser(user)"
				>
					<UserAvatar
						size="sm"
						:name="user.name"
						:label="user.full_name || user.name"
						:image="user.user_image"
					/>
					<span>+ {{ user.full_name || user.name }}</span>
				</button>
			</div>
		</div>

		<div>
			<label class="mb-1.5 block text-xs text-ink-gray-6">Search users</label>
			<div ref="searchWrap">
				<Autocomplete
					v-model="searchValue"
					size="sm"
					placeholder="Search by name or email…"
					:options="searchOptions"
					:disabled="saving"
					@update:query="onSearchQuery"
					@update:model-value="onSearchSelect"
				/>
			</div>
		</div>

		<ErrorMessage v-if="error" :message="error" />
	</div>
</template>

<script setup>
import { computed, nextTick, ref, watch } from "vue"
import { Autocomplete, call, createResource, debounce, toast } from "frappe-ui"
import UserAvatar from "@spa/components/UserAvatar.vue"

const props = defineProps({
	modelValue: { type: Array, default: () => [] },
	/** [{ name, full_name, user_image }] for currently assigned users */
	assigneeDetails: { type: Array, default: () => [] },
	shortlistUsers: { type: Array, default: () => [] },
	/** When set with documentName, persists on each change */
	apiPrefix: { type: String, default: "" },
	documentName: { type: String, default: "" },
	/** Issue uses set_assignees; Task uses set_task_assignees */
	methodName: { type: String, default: "set_assignees" },
})

const emit = defineEmits(["update:modelValue", "updated"])

const saving = ref(false)
const error = ref("")
const searchValue = ref(null)
const searchText = ref("")
const labelCache = ref({})
const imageCache = ref({})
const searchWrap = ref(null)

const selectedNames = computed(() =>
	(props.modelValue || []).filter(Boolean).map((u) => (typeof u === "string" ? u : u.name))
)

const selected = computed(() =>
	selectedNames.value.map((name) => ({
		name,
		full_name: labelCache.value[name] || name,
		user_image: imageCache.value[name] || "",
	}))
)

const availableShortlist = computed(() =>
	(props.shortlistUsers || []).filter((u) => u?.name && !selectedNames.value.includes(u.name))
)

watch(
	() => [props.assigneeDetails, props.shortlistUsers, props.modelValue],
	() => {
		const nextLabels = { ...labelCache.value }
		const nextImages = { ...imageCache.value }
		for (const u of props.assigneeDetails || []) {
			if (u?.name) {
				nextLabels[u.name] = u.full_name || u.name
				if (u.user_image) nextImages[u.name] = u.user_image
			}
		}
		for (const u of props.shortlistUsers || []) {
			if (u?.name) {
				nextLabels[u.name] = u.full_name || u.name
				if (u.user_image) nextImages[u.name] = u.user_image
			}
		}
		for (const name of selectedNames.value) {
			if (!nextLabels[name]) nextLabels[name] = name
		}
		labelCache.value = nextLabels
		imageCache.value = nextImages
	},
	{ immediate: true, deep: true }
)

const linkResource = createResource({
	url: "frappe.desk.search.search_link",
	method: "POST",
	params: {
		doctype: "User",
		txt: "",
		filters: { enabled: 1, user_type: "System User" },
	},
	transform: (data) => {
		const mapped = (data || []).map((doc) => {
			let title = null
			if (doc.label && doc.label !== doc.value) title = doc.label
			else if (doc.description) title = doc.description.split(",")[0]
			const label = title || doc.value
			if (doc.value) {
				labelCache.value = { ...labelCache.value, [doc.value]: label }
			}
			return { label: title ? `${title} (${doc.value})` : doc.value, value: doc.value }
		})
		return mapped.filter((o) => o.value && !selectedNames.value.includes(o.value))
	},
})

const searchOptions = computed(() => linkResource.data || [])

function reloadSearch(txt) {
	linkResource.update({
		params: {
			doctype: "User",
			txt: txt || "",
			filters: { enabled: 1, user_type: "System User" },
		},
	})
	linkResource.reload()
}

const onSearchQuery = debounce((query) => {
	const val = query || ""
	if (searchText.value === val) return
	searchText.value = val
	reloadSearch(val)
}, 300)

reloadSearch("")

function focusSearch() {
	nextTick(() => {
		const input = searchWrap.value?.querySelector("input")
		if (input) {
			input.focus()
			input.select?.()
		}
	})
}

async function ensureUserImage(name) {
	if (!name || imageCache.value[name]) return
	try {
		const image = await call("frappe.client.get_value", {
			doctype: "User",
			filters: { name },
			fieldname: "user_image",
		})
		const url = image?.user_image || image?.message?.user_image || ""
		if (url) {
			imageCache.value = { ...imageCache.value, [name]: url }
		}
	} catch (e) {
		/* ignore */
	}
}

async function persist(nextNames, previousNames) {
	emit("update:modelValue", nextNames)
	if (!props.apiPrefix || !props.documentName) return

	saving.value = true
	error.value = ""
	try {
		const updated = await call(`${props.apiPrefix}.${props.methodName}`, {
			name: props.documentName,
			users: nextNames,
		})
		emit("updated", updated)
	} catch (e) {
		emit("update:modelValue", previousNames)
		error.value = e?.messages?.[0] || e?.message || "Could not update assignees"
		toast.error(error.value)
	} finally {
		saving.value = false
	}
}

async function addUser(user) {
	const name = typeof user === "string" ? user : user?.name || user?.value
	if (!name || selectedNames.value.includes(name) || saving.value) return
	const fullName =
		(typeof user === "object" && (user.full_name || user.label)) || labelCache.value[name] || name
	labelCache.value = { ...labelCache.value, [name]: fullName }
	if (typeof user === "object" && user.user_image) {
		imageCache.value = { ...imageCache.value, [name]: user.user_image }
	} else {
		await ensureUserImage(name)
	}
	const previous = [...selectedNames.value]
	await persist([...previous, name], previous)
	searchValue.value = null
	searchText.value = ""
	reloadSearch("")
	focusSearch()
}

async function removeUser(name) {
	if (!name || saving.value) return
	const previous = [...selectedNames.value]
	await persist(
		previous.filter((u) => u !== name),
		previous
	)
}

function onSearchSelect(val) {
	if (!val) return
	const name = typeof val === "object" ? val.value : val
	const label = typeof val === "object" ? val.label : val
	if (name) {
		if (label && typeof label === "string") {
			const clean = label.includes("(") ? label.split("(")[0].trim() : label
			labelCache.value = { ...labelCache.value, [name]: clean || name }
		}
		addUser({ name, full_name: labelCache.value[name] || name })
	}
	searchValue.value = null
}
</script>
