<template>
	<div ref="root">
		<div v-if="!checklist.items?.length" class="mb-3 text-sm text-gray-500 dark:text-gray-400">
			No items yet
		</div>

		<div v-else class="mb-3 space-y-2">
			<div
				v-for="(item, index) in displayItems"
				:key="item.name"
				:data-item="item.name"
				class="group rounded-lg border bg-white dark:bg-gray-900"
				:class="[
					expandedItem === item.name
						? 'border-gray-900 shadow-sm ring-1 ring-gray-900/10 dark:border-gray-200 dark:ring-gray-200/20'
						: 'cursor-pointer border-gray-200 hover:border-gray-300 hover:bg-gray-50 dark:border-gray-700 dark:hover:border-gray-600 dark:hover:bg-gray-800/60',
					savingItem === item.name ? 'opacity-60' : '',
					itemMotionClass(item),
				]"
				:style="itemStyle(item, index)"
				role="button"
				:tabindex="expandedItem === item.name ? -1 : 0"
				@pointerdown="(e) => pressItem(item, e)"
				@click.stop="onCardClick(item)"
				@keydown.enter.prevent="expand(item)"
				@keydown.alt.up="(e) => nudgeItem(item, -1, e)"
				@keydown.alt.down="(e) => nudgeItem(item, 1, e)"
			>
				<!-- Collapsed -->
				<div v-if="expandedItem !== item.name" class="flex items-start gap-3 px-3 py-2.5">
					<!-- Drag hint (#1919): the whole item drags; the grip shows it can. Alt+↑/↓ on a
					     focused item moves it too. -->
					<button
						v-if="canReorder"
						type="button"
						tabindex="-1"
						class="-ml-1.5 mt-0.5 flex h-5 w-4 flex-shrink-0 cursor-grab touch-none items-center justify-center rounded text-ink-gray-4 opacity-0 hover:text-ink-gray-7 focus:outline-none focus-visible:opacity-100 focus-visible:ring-2 focus-visible:ring-outline-gray-4 group-hover:opacity-100 group-focus-visible:opacity-100"
						:class="reorder?.name === item.name ? 'opacity-100' : ''"
						:title="__('Drag to move, or Alt+↑/↓')"
						:aria-label="__('Drag to move, or Alt+↑/↓')"
						@click.stop
						@keydown.enter.stop.prevent
						@pointerdown.stop="(e) => pressItem(item, e, true)"
					>
						<FeatherIcon name="more-vertical" class="h-4 w-4" />
					</button>
					<div class="min-w-0 flex-1">
						<div
							v-if="(item.description || '').trim()"
							class="truncate text-sm font-medium text-gray-900 dark:text-gray-100"
						>
							{{ item.description }}
						</div>
						<div
							v-if="hasNote(item)"
							class="prose-sm dark:prose-invert max-w-none text-gray-900 dark:text-gray-100 [&_p]:my-0.5"
							:class="(item.description || '').trim() ? 'mt-0.5 text-gray-600 dark:text-gray-300' : ''"
							v-html="item.note"
						/>
						<span
							v-else-if="!(item.description || '').trim()"
							class="text-sm text-gray-400 dark:text-gray-500"
						>
							Click to edit…
						</span>
						<a
							v-if="item.document && item.record"
							:href="deskRecordUrl(item.document, item.record)"
							target="_blank"
							rel="noopener noreferrer"
							class="mt-1 inline-flex max-w-full items-center gap-1 truncate text-xs font-medium text-ink-gray-7 underline-offset-2 hover:text-ink-gray-9 hover:underline"
							:title="`Open ${item.document} ${item.record}`"
							@click.stop
						>
							<span class="truncate">{{ item.document }} · {{ item.record }}</span>
							<FeatherIcon name="external-link" class="h-3 w-3 flex-shrink-0" />
						</a>
						<div
							v-else-if="item.document"
							class="mt-1 truncate text-xs text-ink-gray-5"
						>
							{{ item.document }}
						</div>
						<div
							v-if="item.assigned_to || item.due_date"
							class="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-gray-5"
						>
							<span v-if="item.assigned_to" class="inline-flex min-w-0 items-center gap-1" title="Assigned to">
								<UserAvatar
									:name="item.assigned_to"
									:label="item.assigned_to_name || item.assigned_to"
									size="xs"
								/>
								<span class="truncate">{{ item.assigned_to_name || item.assigned_to }}</span>
							</span>
							<span
								v-if="item.due_date"
								:class="isOverdue(item) ? 'font-medium text-red-600 dark:text-red-400' : ''"
								:title="isOverdue(item) ? 'Overdue' : 'Due date'"
							>
								{{ formatDate(item.due_date) }}
							</span>
						</div>
					</div>
					<div class="flex-shrink-0 pt-0.5" @click.stop>
						<input
							type="checkbox"
							class="h-5 w-5 rounded-full border-gray-300 text-green-600 focus:ring-green-600 dark:border-gray-600 dark:text-green-500 dark:focus:ring-green-500"
							:checked="!!item.done"
							:disabled="savingItem === item.name"
							@change="saveField(item, 'done', $event.target.checked ? 1 : 0, $event)"
						/>
					</div>
				</div>

				<!-- Expanded. A click on its free area closes it again (#1921); clicks in its fields,
				     editor, buttons and links don't. -->
				<div
					v-else
					class="space-y-3 px-3 py-3"
					@pointerdown="onOpenCardPointerDown"
					@pointerup="onOpenCardPointerUp"
					@click.stop="onOpenCardClick"
				>
					<div class="flex items-start gap-3">
						<div class="min-w-0 flex-1 space-y-2">
							<input
								v-model="autosave.draft.description"
								type="text"
								class="w-full rounded-md border border-gray-300 bg-white px-2 py-1.5 text-sm text-gray-900 disabled:opacity-60 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
								:disabled="savingItem === item.name || !!locks.lockedBy(lockField('description', item))"
								:title="lockTitle('description', item)"
								placeholder="Short description"
								maxlength="140"
								@focus="onFieldFocus('description', item)"
								@blur="onFieldBlur('description', item)"
							/>
							<RichTextField
								:key="item.name"
								v-model="autosave.draft.note"
								:fixed-menu="editorMenu"
								:locked-by="locks.lockedBy(lockField('note', item))"
								field-label="this note"
								scroll-hint
								placeholder="Item note…"
								:editor-class="
									compact
										? 'prose-sm dark:prose-invert min-h-[72px] max-h-[180px] overflow-y-auto px-2 py-1.5 border border-gray-200 rounded-md bg-white dark:border-gray-600 dark:bg-gray-800'
										: 'prose-sm dark:prose-invert min-h-[96px] max-h-[220px] overflow-y-auto px-2 py-1.5 border border-gray-200 rounded-md bg-white dark:border-gray-600 dark:bg-gray-800'
								"
								@focus="onFieldFocus('note', item)"
								@blur="onFieldBlur('note', item)"
							/>
						</div>
						<div class="flex flex-shrink-0 flex-col items-center gap-2 pt-1" @click.stop>
							<input
								type="checkbox"
								class="h-5 w-5 rounded-full border-gray-300 text-green-600 focus:ring-green-600 dark:border-gray-600 dark:text-green-500 dark:focus:ring-green-500"
								:checked="!!item.done"
								:disabled="savingItem === item.name"
								@change="saveField(item, 'done', $event.target.checked ? 1 : 0, $event)"
							/>
							<button
								type="button"
								class="flex h-6 w-6 items-center justify-center rounded text-ink-gray-5 hover:bg-surface-gray-2 hover:text-ink-gray-8 focus:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
								:title="__('Collapse')"
								:aria-label="__('Collapse')"
								@click="collapse()"
							>
								<FeatherIcon name="chevron-up" class="h-4 w-4" />
							</button>
						</div>
					</div>
					<div class="space-y-1.5 border-t border-gray-100 pt-3 dark:border-gray-800">
						<label class="block text-[11px] font-medium text-gray-500 dark:text-gray-400">
							Document
						</label>
						<FrappeLink
							doctype="DocType"
							:model-value="item.document || ''"
							placeholder="DocType"
							:disabled="savingItem === item.name"
							@update:model-value="(val) => onDocumentChange(item, val)"
						/>
						<template v-if="item.document">
							<label class="mt-2 block text-[11px] font-medium text-gray-500 dark:text-gray-400">
								Record
							</label>
							<div class="flex items-center gap-2">
								<FrappeLink
									class="min-w-0 flex-1"
									:doctype="item.document"
									:model-value="item.record || ''"
									placeholder="Record"
									:disabled="savingItem === item.name"
									@update:model-value="(val) => saveField(item, 'record', val)"
								/>
								<a
									v-if="item.record"
									:href="deskRecordUrl(item.document, item.record)"
									target="_blank"
									rel="noopener noreferrer"
									class="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded border border-outline-gray-2 text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-9"
									:title="`Open ${item.document} ${item.record}`"
									@click.stop
								>
									<FeatherIcon name="external-link" class="h-3.5 w-3.5" />
								</a>
							</div>
						</template>
					</div>
					<div class="grid grid-cols-2 gap-3 border-t border-gray-100 pt-3 dark:border-gray-800">
						<div class="min-w-0 space-y-1.5">
							<label class="block text-[11px] font-medium text-gray-500 dark:text-gray-400">
								Assigned to
							</label>
							<FrappeLink
								doctype="User"
								query="phamos.api.checklist_inbox.checklist_owner_query"
								:model-value="item.assigned_to || ''"
								placeholder="User"
								:disabled="savingItem === item.name"
								@update:model-value="(val) => onAssignedToChange(item, val)"
							/>
						</div>
						<div class="min-w-0 space-y-1.5">
							<label class="block text-[11px] font-medium text-gray-500 dark:text-gray-400">
								Due date
							</label>
							<FormControl
								type="date"
								size="sm"
								:model-value="item.due_date || ''"
								:disabled="savingItem === item.name"
								@update:model-value="(val) => onDueDateChange(item, val)"
							/>
						</div>
					</div>
					<!-- Move to another checklist of the same record (#1920) -->
					<div v-if="siblingOptions.length" class="flex justify-end border-t border-gray-100 pt-2 dark:border-gray-800">
						<Dropdown :options="siblingOptions.map((o) => ({ ...o, onClick: () => moveToChecklist(item, o.name) }))" placement="right">
							<Button
								variant="ghost"
								size="sm"
								icon-left="corner-up-right"
								:label="__('Move to checklist…')"
								:loading="movingItem === item.name"
								:disabled="savingItem === item.name"
							/>
						</Dropdown>
					</div>
				</div>
			</div>
		</div>

		<div class="flex flex-wrap items-center justify-between gap-2">
			<Button :loading="adding" size="sm" @click="addItem">Add item</Button>
			<Button
				v-if="deskUrl"
				variant="ghost"
				theme="gray"
				size="sm"
				icon-left="external-link"
				label="Open in Desk"
				:link="deskUrl"
			/>
		</div>
	</div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { Button, call, Dropdown, FormControl, toast } from "frappe-ui"
import FrappeLink from "@spa/components/FrappeLink.vue"
import UserAvatar from "@spa/components/UserAvatar.vue"
import RichTextField from "@spa/components/RichTextField.vue"
import { useAutosaveDoc } from "@spa/composables/useAutosaveDoc.js"
import { useDocRealtime } from "@spa/composables/useDocRealtime.js"
import { useFieldLocks } from "@spa/composables/useFieldLocks.js"
import { compareModified, isEmptyHtml } from "@spa/utils/autosaveCore.js"
import { lockMessage } from "@spa/utils/fieldLockText.js"
import { deskRecordUrl } from "@spa/utils/deskUrl.js"
import { formatDate, todayIsoInUserTz } from "@spa/utils/datetime.js"
import { skipTextEditorToolbarTabStops } from "@spa/utils/textEditorFocus.js"
import { __ } from "@spa/utils/i18n.js"
import { closesOnClick, isInteractiveTarget } from "@spa/utils/interactiveTarget.js"
import { dragOffsets, dropIndex, moved, passedDragDistance } from "@spa/utils/listReorder.js"

const props = defineProps({
	checklist: { type: Object, required: true },
	compact: { type: Boolean, default: false },
})

const emit = defineEmits(["updated", "moved"])

const deskUrl = computed(
	() => props.checklist.desk_url || (props.checklist.name ? `/app/checklist/${props.checklist.name}` : "")
)

const API = "phamos.api.checklist_inbox"
const editorMenu = [
	"Paragraph",
	"Bold",
	"Italic",
	"Link",
	"Separator",
	"Bullet List",
	"Numbered List",
]

const root = ref(null)
const savingItem = ref(null)
const adding = ref(false)
const expandedItem = ref(null)

async function focusFirstField() {
	// The description input is rendered immediately, but wait a tick so the
	// expanded card (and its input) is actually in the DOM first.
	for (let i = 0; i < 20; i++) {
		await nextTick()
		const input = root.value?.querySelector('input[type="text"]')
		if (input?.isConnected) {
			input.focus()
			return
		}
		await new Promise((resolve) => setTimeout(resolve, 20))
	}
}

// The expanded item's description and note autosave like the Issue/Task
// fields (GitLab #1426). The autosave key combines checklist and item so a
// save that finishes after switching checklists still targets the right one.
const KEY_SEPARATOR = "::"

function itemKey(itemName) {
	return `${props.checklist.name}${KEY_SEPARATOR}${itemName}`
}

function splitKey(key) {
	const at = key.indexOf(KEY_SEPARATOR)
	return { checklistName: key.slice(0, at), itemName: key.slice(at + KEY_SEPARATOR.length) }
}

function itemDoc(checklist, itemName, key) {
	const item = (checklist?.items || []).find((row) => row.name === itemName)
	if (!item) return null
	return {
		name: key,
		description: item.description || "",
		note: item.note || "",
		modified: checklist.modified,
		modified_by: checklist.modified_by,
		modified_by_name: checklist.modified_by_name,
	}
}

const autosave = useAutosaveDoc({
	doc: () => (expandedItem.value ? itemDoc(props.checklist, expandedItem.value, itemKey(expandedItem.value)) : null),
	fields: {
		description: { kind: "text", label: "Description" },
		note: { kind: "html", label: "Note" },
	},
	// update_checklist_item retries on its own; items carry no timestamp lock.
	useModified: false,
	request: (key, payload) => {
		const { checklistName, itemName } = splitKey(key)
		return {
			method: `${API}.update_spa_checklist_item`,
			args: { checklist_name: checklistName, item_name: itemName, values: payload },
		}
	},
	parse: (checklist, key) => {
		emit("updated", checklist)
		return itemDoc(checklist, splitKey(key).itemName, key) || { name: key }
	},
	fetch: async (key) => {
		const checklist = await call(`${API}.get_checklist`, { name: splitKey(key).checklistName })
		return itemDoc(checklist, splitKey(key).itemName, key)
	},
	readonly: () => !expandedItem.value,
})

const realtime = useDocRealtime({
	doctype: "Checklist",
	name: () => props.checklist.name,
	onDocUpdate: onRemoteUpdate,
})

const locks = useFieldLocks({
	doctype: "Checklist",
	name: () => props.checklist.name,
	realtime,
	onReleased: () => {
		if (autosave.status === "blocked") autosave.flush()
	},
})

function lockField(field, item) {
	return `${field}:${item.name}`
}

function lockTitle(field, item) {
	const lock = locks.lockedBy(lockField(field, item))
	return lock ? lockMessage(lock, "this description") : ""
}

async function onFieldFocus(field, item) {
	autosave.setFocused(field, true)
	await locks.acquire(lockField(field, item))
}

async function onFieldBlur(field, item) {
	const docname = props.checklist.name
	await autosave.setFocused(field, false)
	locks.release(lockField(field, item), { docname })
}

async function onRemoteUpdate(modified) {
	if (compareModified(modified, props.checklist.modified) <= 0) return
	const name = props.checklist.name
	try {
		const latest = await call(`${API}.get_checklist`, { name })
		// The parent replaces `checklist`; the autosave merge keeps whatever the
		// user is typing in the expanded item.
		if (latest?.name === props.checklist.name) emit("updated", latest)
	} catch (e) {
		// Ignore; the next save or reload brings the latest state.
	}
}

function hasNote(item) {
	const live = expandedItem.value === item.name && autosave.currentName === itemKey(item.name)
	return !isEmptyHtml(live ? autosave.draft.note : item.note)
}

function itemDescription(item) {
	const live = expandedItem.value === item.name && autosave.currentName === itemKey(item.name)
	return live ? autosave.draft.description : item.description
}

function isEmptyItem(item) {
	return (
		!hasNote(item) &&
		!(itemDescription(item) || "").trim() &&
		!(item.document || "").trim() &&
		!(item.record || "").trim() &&
		!item.assigned_to &&
		!item.due_date
	)
}

function findItem(name) {
	return (props.checklist.items || []).find((row) => row.name === name) || null
}

async function removeEmptyItem(item) {
	if (!item?.name || !isEmptyItem(item)) return
	savingItem.value = item.name
	try {
		const updated = await call(`${API}.delete_spa_checklist_item`, {
			checklist_name: props.checklist.name,
			item_name: item.name,
		})
		emit("updated", updated)
	} finally {
		savingItem.value = null
	}
}

async function collapse() {
	const name = expandedItem.value
	if (!name) return
	// Save what was typed before the item closes (and before deciding whether
	// it is empty), then read the item back from the refreshed checklist.
	await autosave.flush()
	await nextTick()
	const item = findItem(name)
	expandedItem.value = null
	if (item) await removeEmptyItem(item)
}

async function expand(item) {
	if (expandedItem.value === item.name) return
	await collapse()
	expandedItem.value = item.name
	skipTextEditorToolbarTabStops(root.value)
}

// Reordering (#1919): press anywhere on a collapsed item and move it (a mouse after a few pixels,
// a finger after holding still for a moment), drag its grip, or Alt+↑/↓ on a focused item.
// While dragging, the DOM order stays as it is: the item follows the pointer and the items it
// passes slide aside (transforms only), so nothing jumps and no element is moved under the pointer.
// On release the new order shows at once and is saved in the background.
const TOUCH_HOLD_MS = 350
const TOUCH_SLOP = 8 // px a finger may wander during the hold; more is a scroll
const AUTOSCROLL_EDGE = 40 // px from the scroll box's edge where the list scrolls by itself
const reorder = ref(null) // { name, pointerId, from, to, dy }
const reorderSaving = ref(false)
const pendingOrder = ref(null) // item names as just dropped, until the saved list arrives
let press = null // { item, pointerId, x, y, touch, timer }
let reorderRects = []
let reorderStep = 0
let startListY = 0
let lastClientY = 0
let scrollBox = null
let scrollFrame = 0
let suppressClick = false

const canReorder = computed(() => (props.checklist.items?.length || 0) > 1)
const displayItems = computed(() => {
	const items = props.checklist.items || []
	if (!pendingOrder.value) return items
	const byName = new Map(items.map((i) => [i.name, i]))
	const ordered = pendingOrder.value.map((n) => byName.get(n)).filter(Boolean)
	return ordered.length === items.length ? ordered : items
})
// the saved list (or any other reload) replaces the order shown while saving
watch(
	() => props.checklist.items,
	() => (pendingOrder.value = null)
)
const reorderOffsets = computed(() => {
	const r = reorder.value
	return r ? dragOffsets(displayItems.value.length, r.from, r.to, reorderStep) : []
})

function itemStyle(item, index) {
	const r = reorder.value
	if (!r) return null
	const y = item.name === r.name ? r.dy : reorderOffsets.value[index] || 0
	return y ? { transform: `translateY(${y}px)` } : null
}

function itemMotionClass(item) {
	const r = reorder.value
	if (!r) return "transition-colors"
	return r.name === item.name
		? "relative z-10 cursor-grabbing shadow-lg ring-2 ring-outline-gray-3"
		: "transition-transform duration-150 ease-out"
}

const itemEl = (name) => root.value?.querySelector(`[data-item="${CSS.escape(name)}"]`)
const listTop = () => root.value?.getBoundingClientRect().top || 0

function scrollParent(el) {
	for (let node = el?.parentElement; node; node = node.parentElement) {
		const overflowY = getComputedStyle(node).overflowY
		if ((overflowY === "auto" || overflowY === "scroll") && node.scrollHeight > node.clientHeight) return node
	}
	return null
}

/** A press on a collapsed item (or its grip, `fromGrip`): becomes a drag or stays a click. */
function pressItem(item, event, fromGrip = false) {
	if (event.button !== 0 || press || reorder.value || !canReorder.value) return
	if (!fromGrip && (expandedItem.value === item.name || isInteractiveTarget(event.target, event.currentTarget))) return
	press = {
		item,
		pointerId: event.pointerId,
		x: event.clientX,
		y: event.clientY,
		touch: event.pointerType === "touch",
		timer: 0,
	}
	// Follow the pointer on the window, not with pointer capture: a captured element that is moved
	// in the DOM loses the capture, which once ended every upward drag at once. Events of other
	// pointers (a second finger) are ignored by pointerId.
	window.addEventListener("pointermove", onPressMove)
	window.addEventListener("pointerup", onPressUp)
	window.addEventListener("pointercancel", onPressCancel)
	if (fromGrip) startDrag(event.clientY)
	else if (press.touch) press.timer = setTimeout(() => startDrag(press.y), TOUCH_HOLD_MS)
}

function onPressMove(event) {
	if (!press || event.pointerId !== press.pointerId) return
	if (reorder.value) {
		// only while the button is down: a lost release must not keep moving the item
		if (!press.touch && (event.buttons & 1) !== 1) return endPress()
		return dragTo(event.clientY)
	}
	const dx = event.clientX - press.x
	const dy = event.clientY - press.y
	if (press.touch) {
		if (Math.hypot(dx, dy) > TOUCH_SLOP) endPress() // the finger scrolls
		return
	}
	if ((event.buttons & 1) !== 1) return endPress()
	if (passedDragDistance(dx, dy)) startDrag(press.y, event.clientY)
}

function onPressUp(event) {
	if (!press || event.pointerId !== press.pointerId) return
	if (reorder.value) return dropItem()
	endPress() // a click: the card's click handler opens the item
}

function onPressCancel(event) {
	if (!press || event.pointerId !== press.pointerId) return
	endPress()
}

function startDrag(fromClientY, nowClientY = fromClientY) {
	if (!press || reorder.value) return
	clearTimeout(press.timer)
	const items = displayItems.value
	const from = items.findIndex((i) => i.name === press.item.name)
	if (from < 0 || reorderSaving.value || savingItem.value) return endPress()
	// the boxes as they are now, relative to the list, so scrolling during the drag doesn't move
	// the drop zones
	const top = listTop()
	reorderRects = items.map((i) => {
		const r = itemEl(i.name)?.getBoundingClientRect()
		return { top: (r?.top || 0) - top, height: r?.height || 0 }
	})
	const gap =
		reorderRects.length > 1 ? Math.max(0, reorderRects[1].top - reorderRects[0].top - reorderRects[0].height) : 0
	reorderStep = reorderRects[from].height + gap
	startListY = fromClientY - top
	reorder.value = { name: press.item.name, pointerId: press.pointerId, from, to: from, dy: 0 }
	window.getSelection?.()?.removeAllRanges()
	document.body.style.userSelect = "none"
	document.body.style.cursor = "grabbing"
	window.addEventListener("touchmove", blockTouchScroll, { passive: false })
	scrollBox = scrollParent(root.value)
	scrollFrame = requestAnimationFrame(autoScroll)
	dragTo(nowClientY)
}

function blockTouchScroll(event) {
	event.preventDefault() // the finger drags the item, not the page
}

function dragTo(clientY) {
	const r = reorder.value
	if (!r) return
	lastClientY = clientY
	const dy = clientY - listTop() - startListY
	const box = reorderRects[r.from]
	// where the item's middle is now decides its slot
	const to = dropIndex(box.top + box.height / 2 + dy, reorderRects, r.from)
	if (dy !== r.dy || to !== r.to) reorder.value = { ...r, dy, to }
}

function autoScroll() {
	scrollFrame = 0
	if (!reorder.value) return
	if (scrollBox) {
		const r = scrollBox.getBoundingClientRect()
		let speed = 0
		if (lastClientY < r.top + AUTOSCROLL_EDGE) speed = lastClientY - (r.top + AUTOSCROLL_EDGE)
		else if (lastClientY > r.bottom - AUTOSCROLL_EDGE) speed = lastClientY - (r.bottom - AUTOSCROLL_EDGE)
		if (speed) {
			const before = scrollBox.scrollTop
			scrollBox.scrollTop += Math.max(-15, Math.min(15, speed / 2))
			if (scrollBox.scrollTop !== before) dragTo(lastClientY)
		}
	}
	scrollFrame = requestAnimationFrame(autoScroll)
}

/** Ends a press or drag without saving anything. */
function endPress() {
	if (press) clearTimeout(press.timer)
	press = null
	window.removeEventListener("pointermove", onPressMove)
	window.removeEventListener("pointerup", onPressUp)
	window.removeEventListener("pointercancel", onPressCancel)
	window.removeEventListener("touchmove", blockTouchScroll)
	cancelAnimationFrame(scrollFrame)
	scrollFrame = 0
	if (reorder.value) {
		document.body.style.userSelect = ""
		document.body.style.cursor = ""
	}
	reorder.value = null
}

async function dropItem() {
	const r = reorder.value
	const shownTop = itemEl(r.name)?.getBoundingClientRect().top
	// the release ends in a click on the card, which would open the item
	suppressClick = true
	setTimeout(() => (suppressClick = false))
	const items = displayItems.value
	if (r.to !== r.from) pendingOrder.value = moved(items, r.from, r.to).map((i) => i.name)
	endPress()
	glideIntoPlace(r.name, shownTop)
	if (r.to === r.from) return
	reorderSaving.value = true
	try {
		await moveItem(r.name, r.to, { quiet: true })
	} finally {
		reorderSaving.value = false
	}
}

/** Slides the dropped item from where it was let go into its slot. */
async function glideIntoPlace(name, shownTop) {
	await nextTick()
	const el = itemEl(name)
	if (!el || shownTop == null || typeof el.animate !== "function") return
	const delta = shownTop - el.getBoundingClientRect().top
	if (Math.abs(delta) < 1) return
	el.animate([{ transform: `translateY(${delta}px)` }, { transform: "translateY(0)" }], {
		duration: 150,
		easing: "ease-out",
	})
}

function onCardClick(item) {
	if (suppressClick) return
	expand(item)
}

async function nudgeItem(item, step, event) {
	// Only on the focused, collapsed item itself: inside an open item's fields Alt+↑/↓ belongs to
	// the field (moving the caret on macOS), and must neither move the item nor be swallowed.
	if (event && (event.target !== event.currentTarget || expandedItem.value === item.name)) return
	event?.preventDefault()
	const items = props.checklist.items || []
	const from = items.findIndex((i) => i.name === item.name)
	const to = from + step
	if (from < 0 || to < 0 || to >= items.length || savingItem.value) return
	await moveItem(item.name, to)
	await nextTick()
	root.value?.querySelector(`[data-item="${CSS.escape(item.name)}"]`)?.focus()
}

/** Saves an item's new position; `quiet` (a drag, already shown) skips the busy state. */
async function moveItem(name, toIndex, { quiet = false } = {}) {
	if (!quiet) savingItem.value = name
	try {
		const updated = await call(`${API}.move_spa_checklist_item`, {
			checklist_name: props.checklist.name,
			item_name: name,
			to_index: toIndex,
		})
		emit("updated", updated)
	} catch (e) {
		toast({
			title: e?.messages?.[0] || e?.message || __("Could not move the item"),
			icon: "x-circle",
			iconClasses: "text-ink-red-4",
		})
		pendingOrder.value = null // back to the saved order
	} finally {
		if (!quiet) savingItem.value = null
	}
}

// Moving an item to another checklist of the same record (#1920). The other checklists are
// loaded once an item opens; the parent reloads both checklists after the move ("moved").
const siblings = ref([])
const movingItem = ref(null)
const siblingOptions = computed(() =>
	siblings.value
		.filter((c) => c.name !== props.checklist.name)
		.map((c) => ({ name: c.name, label: c.title || c.name }))
)

async function loadSiblings() {
	const { document, reference_record: record } = props.checklist
	if (!document || !record) return (siblings.value = [])
	try {
		siblings.value = await call(`${API}.get_checklists_for_reference`, { document, reference_record: record })
	} catch (e) {
		siblings.value = []
	}
}

async function moveToChecklist(item, target) {
	movingItem.value = item.name
	try {
		// what was typed in the item goes with it
		await autosave.flush()
		const result = await call(`${API}.move_spa_checklist_item_to`, {
			checklist_name: props.checklist.name,
			item_name: item.name,
			target_checklist: target,
		})
		expandedItem.value = null
		emit("updated", result.source)
		emit("moved", result)
		toast({ title: __("Moved to {0}", [result.target.title || result.target.name]), icon: "check-circle", iconClasses: "text-ink-green-4" })
	} catch (e) {
		toast({ title: e?.messages?.[0] || e?.message || __("Could not move the item"), icon: "x-circle", iconClasses: "text-ink-red-4" })
	} finally {
		movingItem.value = null
	}
}

// fresh on every opened item: checklists of the record may have been added or renamed since
watch(expandedItem, (name) => {
	if (name) loadSiblings()
})

// A click on an open item's free area closes it (#1921); its fields, editor, buttons and links
// keep their clicks. Only up to the card: the item around it is itself role="button".
// A click is only a "close" when it also started on the free area: selecting text in a field and
// letting go over the free area ends in a click on the card, too (the browser sends the click to
// the element both ends share).
let pressedOnFreeArea = false
let releasedOnField = false
function onOpenCardPointerDown(event) {
	pressedOnFreeArea = !isInteractiveTarget(event.target, event.currentTarget)
	releasedOnField = false
}

function onOpenCardPointerUp(event) {
	releasedOnField = isInteractiveTarget(event.target, event.currentTarget)
}

function onOpenCardClick(event) {
	const close = closesOnClick({
		pressedOnFreeArea,
		releasedOnField,
		clickedOnFreeArea: !isInteractiveTarget(event.target, event.currentTarget),
		selectedText: window.getSelection?.()?.toString() || "",
	})
	pressedOnFreeArea = false
	releasedOnField = false
	if (close) collapse()
}

async function onDocClick(event) {
	if (!expandedItem.value || !root.value) return
	const path = typeof event.composedPath === "function" ? event.composedPath() : []
	const inside = root.value.contains(event.target) || path.includes(root.value)
	if (!inside) await collapse()
}

async function onKeydown(event) {
	if (event.key === "Escape" && expandedItem.value) {
		await collapse()
	}
}

onMounted(() => {
	document.addEventListener("click", onDocClick)
	document.addEventListener("keydown", onKeydown)
})

onBeforeUnmount(() => {
	document.removeEventListener("click", onDocClick)
	document.removeEventListener("keydown", onKeydown)
	endPress()
})

async function saveField(item, field, value, event = null) {
	const values = { [field]: value }
	await autosave.flush()
	savingItem.value = item.name
	try {
		const updated = await call(`${API}.update_spa_checklist_item`, {
			checklist_name: props.checklist.name,
			item_name: item.name,
			values,
		})
		emit("updated", updated)
	} catch (e) {
		if (field === "done" && event?.target) {
			event.target.checked = !value
		}
	} finally {
		savingItem.value = null
	}
}

async function onDocumentChange(item, document) {
	const previousDocument = item.document || ""
	const previousRecord = item.record || ""
	const record = document === previousDocument ? previousRecord : ""
	// Apply locally right away: the Record field only renders once item.document
	// is set (v-if="item.document"), and it needs to exist before Tab is pressed,
	// not after this save round-trips.
	item.document = document
	item.record = record
	await autosave.flush()
	savingItem.value = item.name
	try {
		const updated = await call(`${API}.update_spa_checklist_item`, {
			checklist_name: props.checklist.name,
			item_name: item.name,
			values: { document, record },
		})
		emit("updated", updated)
	} catch (e) {
		item.document = previousDocument
		item.record = previousRecord
	} finally {
		savingItem.value = null
	}
}

// Assignee and due date of an item (#1625): the assignee gets a ToDo for it.
function isOverdue(item) {
	return !item.done && !!item.due_date && item.due_date < todayIsoInUserTz()
}

async function onAssignedToChange(item, user) {
	if ((user || "") === (item.assigned_to || "")) return
	await saveField(item, "assigned_to", user || "")
}

async function onDueDateChange(item, date) {
	if ((date || "") === (item.due_date || "")) return
	await saveField(item, "due_date", date || "")
}

async function addItem() {
	adding.value = true
	let newestName = null
	try {
		const updated = await call(`${API}.add_spa_checklist_item`, {
			checklist_name: props.checklist.name,
			values: {},
		})
		emit("updated", updated)
		const items = updated?.items || []
		const newest = items[items.length - 1]
		newestName = newest?.name || null
		if (newestName) expandedItem.value = newestName
	} finally {
		adding.value = false
	}
	if (newestName) {
		skipTextEditorToolbarTabStops(root.value)
		await focusFirstField()
	}
}
</script>
