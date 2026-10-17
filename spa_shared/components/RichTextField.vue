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
		<!-- Content outside the box (scrollHint): fades at the clipped edges and "More below". -->
		<template v-if="scrollHint">
			<div
				v-show="overflow.above"
				class="pointer-events-none absolute inset-x-px h-6 bg-gradient-to-b from-black/10 to-transparent dark:from-black/40"
				:style="{ top: `${editorTop}px` }"
				aria-hidden="true"
			/>
			<div
				v-show="overflow.below"
				class="pointer-events-none absolute inset-x-px bottom-px flex h-12 items-end justify-center rounded-b-lg bg-gradient-to-t from-white to-transparent pb-1.5 dark:from-gray-800"
			>
				<button
					type="button"
					class="pointer-events-auto inline-flex items-center gap-1 rounded-full border border-outline-gray-2 bg-surface-white px-2.5 py-0.5 text-xs font-medium text-ink-gray-7 shadow-sm hover:text-ink-gray-9"
					:title="__('Scroll to see the rest of the text')"
					@mousedown.prevent
					@click="scrollMore"
				>
					<FeatherIcon name="chevron-down" class="h-3.5 w-3.5" />
					{{ __("More below") }}
				</button>
			</div>
		</template>
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
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { FeatherIcon, TextEditor } from "frappe-ui"
import UserAvatar from "@spa/components/UserAvatar.vue"
import { normalizeHtml } from "@spa/utils/autosaveCore.js"
import { lockExplanation, lockHeadline } from "@spa/utils/fieldLockText.js"
import { scrollOverflow } from "@spa/utils/scrollOverflow.js"
import { __ } from "@spa/utils/i18n.js"

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
	/** The editor scrolls inside a fixed box: show when text is hidden above or below */
	scrollHint: { type: Boolean, default: false },
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

// Scroll hint: watch the editor's own scroll box (.ProseMirror), its size and its content.
const overflow = ref({ above: false, below: false })
const editorTop = ref(0)
let scrollBox = null
let resizeObserver = null
let findFrame = 0

function measure() {
	if (!scrollBox || !root.value) return
	overflow.value = scrollOverflow(scrollBox)
	editorTop.value = scrollBox.getBoundingClientRect().top - root.value.getBoundingClientRect().top
}

function attachScrollHint() {
	findFrame = 0
	const box = root.value?.querySelector(".ProseMirror")
	if (!box) {
		findFrame = requestAnimationFrame(attachScrollHint) // the editor mounts a moment later
		return
	}
	if (box === scrollBox) return measure()
	scrollBox?.removeEventListener("scroll", measure)
	scrollBox = box
	scrollBox.addEventListener("scroll", measure, { passive: true })
	resizeObserver?.disconnect()
	resizeObserver = new ResizeObserver(measure)
	resizeObserver.observe(scrollBox)
	resizeObserver.observe(root.value)
	measure()
}

function scrollMore() {
	scrollBox?.scrollBy({ top: Math.round(scrollBox.clientHeight * 0.8), behavior: "smooth" })
}

onMounted(() => {
	if (props.scrollHint) attachScrollHint()
})
// New content (typing, another user's change) changes the height without resizing the box.
watch(editorContent, () => props.scrollHint && nextTick(measure))
watch(
	() => props.lockedBy,
	() => props.scrollHint && nextTick(attachScrollHint)
)

onBeforeUnmount(() => {
	cancelAnimationFrame(findFrame)
	scrollBox?.removeEventListener("scroll", measure)
	resizeObserver?.disconnect()
	clearTimeout(blurTimer)
	clearInterval(clock)
	if (focused.value) emit("blur")
})

defineExpose({ editor, focused })
</script>
