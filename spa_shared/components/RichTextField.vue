<template>
	<div
		ref="root"
		class="relative"
		:class="$attrs.class"
		@focusin="onFocusIn"
		@focusout="onFocusOut"
	>
		<!-- Takes the toolbar's place while another user holds the field lock. -->
		<div
			v-if="lockedBy"
			class="flex w-full flex-shrink-0 items-start gap-2 rounded-t-lg border border-outline-amber-1 bg-surface-amber-1 px-2 py-1.5 text-xs text-ink-amber-3"
			role="status"
		>
			<UserAvatar
				class="mt-px"
				size="xs"
				:name="lockedBy.user"
				:label="lockedBy.full_name"
				:image="lockedBy.user_image"
			/>
			<div class="min-w-0">
				<div class="font-semibold">{{ lockHeadline(lockedBy, fieldLabel) }}</div>
				<div class="mt-0.5 leading-snug">{{ lockExplanation(lockedBy, now) }}</div>
			</div>
		</div>
		<TextEditor
			ref="editorRef"
			:class="editorRootClass"
			:content="editorContent"
			:editable="editable && !lockedBy"
			:fixed-menu="editable && !lockedBy ? fixedMenu : false"
			:placeholder="placeholder"
			:editor-class="editorClass"
			@change="onChange"
		/>
	</div>
</template>

<script setup>
/**
 * frappe-ui TextEditor that never replaces its content while the user is in it.
 *
 * frappe-ui's TextEditor calls `setContent` whenever its `content` prop differs
 * from the editor HTML, which moves the cursor to the end and drops what was
 * typed in the meantime (GitLab #1426). Here new values from the parent are
 * held back while focus is inside the field (editor or its toolbar) and applied
 * on blur, and values that only differ in formatting noise are ignored.
 *
 * Give it `:key="doc.name"` so switching documents remounts it with a fresh
 * undo history.
 */
import { computed, onBeforeUnmount, ref, watch } from "vue"
import { TextEditor } from "frappe-ui"
import UserAvatar from "@spa/components/UserAvatar.vue"
import { normalizeHtml } from "@spa/utils/autosaveCore.js"
import { lockExplanation, lockHeadline } from "@spa/utils/fieldLockText.js"

defineOptions({ inheritAttrs: false })

const props = defineProps({
	modelValue: { type: String, default: "" },
	editable: { type: Boolean, default: true },
	fixedMenu: { type: [Boolean, Array], default: false },
	placeholder: { type: [String, Function], default: "" },
	editorClass: { type: [String, Array, Object], default: "" },
	editorRootClass: { type: [String, Array, Object], default: "" },
	/** { user, full_name, user_image, expiresAt } of another user holding the field lock */
	lockedBy: { type: Object, default: null },
	/** Used in the lock notice: "<name> is editing <fieldLabel>" */
	fieldLabel: { type: String, default: "this field" },
})

const emit = defineEmits(["update:modelValue", "focus", "blur"])

const root = ref(null)
const editorRef = ref(null)
const editorContent = ref(props.modelValue || "")
const focused = ref(false)
let lastEmitted = props.modelValue || ""
let blurTimer = null

const editor = computed(() => editorRef.value?.editor || null)

function onChange(html) {
	lastEmitted = html
	// Keep the prop in step with the editor so frappe-ui's watcher stays idle.
	editorContent.value = html
	emit("update:modelValue", html)
}

function push(value) {
	value = value || ""
	lastEmitted = value
	const current = editor.value ? editor.value.getHTML() : editorContent.value
	if (normalizeHtml(current) === normalizeHtml(value)) return
	editorContent.value = value
}

watch(
	() => props.modelValue,
	(value) => {
		if (value === lastEmitted) return
		if (focused.value) return // applied on blur
		push(value)
	}
)

// Ticks once a second while locked so the automatic-unlock countdown is live.
const now = ref(Date.now())
let clock = null

watch(
	() => props.lockedBy,
	(lock) => {
		if (lock && focused.value) editor.value?.commands?.blur?.()
		clearInterval(clock)
		clock = null
		if (lock) {
			now.value = Date.now()
			clock = setInterval(() => (now.value = Date.now()), 1000)
		}
	},
	{ immediate: true }
)

function onFocusIn() {
	clearTimeout(blurTimer)
	if (focused.value) return
	focused.value = true
	emit("focus")
}

function onFocusOut() {
	clearTimeout(blurTimer)
	// Toolbar clicks blur and refocus the editor; wait before deciding.
	blurTimer = setTimeout(() => {
		if (root.value?.contains(document.activeElement)) return
		if (!focused.value) return
		focused.value = false
		push(props.modelValue)
		emit("blur")
	}, 150)
}

onBeforeUnmount(() => {
	clearTimeout(blurTimer)
	clearInterval(clock)
	if (focused.value) emit("blur")
})

defineExpose({ editor, focused })
</script>
