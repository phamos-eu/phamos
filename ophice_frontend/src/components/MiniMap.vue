<template>
	<!--
		The mini map over an open cockpit (#2074): the office live, small and draggable, with pings
		(someone walks up, a message, a notice) and quick replies. "Full screen" goes back to the map;
		"Float" (Chrome, Edge, newer Firefox) puts it in a small window that stays on top of everything.
	-->
	<Teleport :to="floatTarget || 'body'" :disabled="!floatTarget">
		<div
			ref="root"
			class="mini-map flex flex-col overflow-hidden rounded-xl border border-outline-gray-3 bg-surface-white text-ink-gray-9 shadow-2xl"
			:class="floatTarget ? 'mini-map--floating' : 'fixed z-[60]'"
			:style="floatTarget ? {} : { left: `${pos.x}px`, top: `${pos.y}px`, width: `${WIDTH}px` }"
			data-testid="mini-map"
		>
			<header
				class="flex flex-shrink-0 select-none items-center gap-1.5 border-b border-outline-gray-2 px-2 py-1.5"
				:class="floatTarget ? '' : 'cursor-move'"
				@pointerdown="startDrag"
			>
				<img :src="OPHICE_ICON" alt="" class="h-4 w-4 rounded" />
				<span class="min-w-0 flex-1 truncate text-xs font-medium">{{ __("Ophice") }}</span>
				<span
					v-if="noticeCount"
					class="rounded-full bg-surface-red-5 px-1.5 text-[10px] font-semibold leading-4 text-ink-white"
					:title="__('{0} notices on the map', [noticeCount])"
				>
					{{ noticeCount }}
				</span>
				<button
					v-if="canFloat && !floatTarget"
					type="button"
					class="rounded p-1 text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-9"
					:title="__('Float: keep the map on top of all windows')"
					data-testid="mini-map-float"
					@pointerdown.stop
					@click="float"
				>
					<FeatherIcon name="copy" class="h-3.5 w-3.5" />
				</button>
				<button
					type="button"
					class="rounded p-1 text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-9"
					:title="__('Back to the map, full screen (the cockpit stays open)')"
					data-testid="mini-map-fullscreen"
					@pointerdown.stop
					@click="$emit('fullscreen')"
				>
					<FeatherIcon name="maximize-2" class="h-3.5 w-3.5" />
				</button>
			</header>

			<!-- The office, small -->
			<div class="relative flex-shrink-0 overflow-hidden" :style="mapStyle" @dblclick="$emit('fullscreen')">
				<div
					v-for="area in areas"
					:key="area.name"
					class="absolute rounded-sm"
					:style="areaStyle(area)"
				/>
				<span
					v-for="chip in others"
					:key="chip.user"
					class="mini-map__chip absolute rounded-full"
					:class="{ 'opacity-40': chip.offline }"
					:style="chipStyle(chip, chip.guest ? 'rgb(217,119,6)' : `hsl(${ringHue(chip.user)} 80% 45%)`)"
					:title="chip.full_name"
				/>
				<span v-if="me" class="mini-map__chip mini-map__chip--me absolute rounded-full" :style="chipStyle(me, 'rgb(37,99,235)')" :title="__('You')" />
			</div>

			<!-- Pings: newest first -->
			<div v-if="pings.length" class="max-h-64 space-y-1.5 overflow-y-auto border-t border-outline-gray-2 p-2" data-testid="mini-map-pings">
				<div
					v-for="ping in pings"
					:key="ping.id"
					class="rounded-lg bg-surface-gray-1 p-2 text-xs"
					:class="{ 'mini-map__ping--new': ping.fresh }"
					data-testid="mini-map-ping"
				>
					<div class="flex items-start gap-1.5">
						<FeatherIcon :name="ICONS[ping.kind] || 'bell'" class="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-ink-gray-6" />
						<p class="min-w-0 flex-1 text-ink-gray-8">{{ ping.text }}</p>
						<button type="button" class="rounded p-0.5 text-ink-gray-5 hover:bg-surface-gray-3" :title="__('Close')" @click="$emit('dismiss', ping)">
							<FeatherIcon name="x" class="h-3 w-3" />
						</button>
					</div>
					<!-- Answer right here, without leaving the cockpit (PM, 2026-11-22) -->
					<template v-if="ping.kind !== 'reminder'">
						<p v-for="(line, index) in ping.replies || []" :key="index" class="mt-1 text-[11px] text-ink-gray-6">
							{{ __("You: {0}", [line]) }}
						</p>
						<form class="mt-1.5 flex items-center gap-1" @submit.prevent="reply(ping)">
							<input
								v-model="drafts[ping.id]"
								type="text"
								maxlength="1000"
								class="h-7 min-w-0 flex-1 rounded border border-outline-gray-2 bg-surface-white px-2 text-xs text-ink-gray-9"
								:placeholder="ping.kind === 'meeting' ? __('Reply in the meeting chat') : __('Reply')"
								data-testid="mini-map-reply-input"
								@keydown.stop
							/>
							<button
								type="submit"
								class="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded bg-surface-gray-7 text-ink-white disabled:opacity-40"
								:disabled="!(drafts[ping.id] || '').trim() || sending[ping.id]"
								:title="__('Send')"
							>
								<FeatherIcon name="send" class="h-3.5 w-3.5" />
							</button>
						</form>
					</template>
					<!-- Someone walked up: answer without leaving the cockpit -->
					<div v-if="ping.kind === 'walkup'" class="mt-1.5 space-y-1">
						<p class="text-[11px] text-ink-gray-5">{{ __("I'll get back to you in") }}</p>
						<div class="flex flex-wrap gap-1">
							<button
								v-for="minutes in MINUTES"
								:key="minutes"
								type="button"
								class="rounded-full bg-surface-white px-2 py-0.5 text-[11px] font-medium shadow-sm hover:bg-surface-gray-2"
								data-testid="mini-map-reply"
								@click="$emit('reply', ping, minutes)"
							>
								{{ __("{0} min", [minutes]) }}
							</button>
						</div>
						<div class="flex flex-wrap gap-1 pt-0.5">
							<button
								type="button"
								class="rounded-full bg-surface-gray-7 px-2 py-0.5 text-[11px] font-medium text-ink-white hover:opacity-90"
								@click="$emit('open-chat', ping)"
							>
								{{ __("Open the chat") }}
							</button>
							<!-- #2068: depends on the calendar sync -->
							<button
								type="button"
								disabled
								class="cursor-not-allowed rounded-full bg-surface-white px-2 py-0.5 text-[11px] text-ink-gray-4"
								:title="__('Coming soon')"
							>
								{{ __("Book an appointment with me") }} · {{ __("coming soon") }}
							</button>
						</div>
					</div>
					<div v-else-if="ping.kind !== 'reminder'" class="mt-1.5">
						<button
							type="button"
							class="rounded-full bg-surface-white px-2 py-0.5 text-[11px] font-medium shadow-sm hover:bg-surface-gray-2"
							@click="$emit('open-chat', ping)"
						>
							{{ __("Show on the map") }}
						</button>
					</div>
				</div>
			</div>
		</div>
	</Teleport>
</template>

<script setup>
import { computed, onBeforeUnmount, reactive, ref } from "vue"
import { FeatherIcon } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"
import { ringHue } from "../utils/ophiceColor.js"
import { canFloat, openFloatingWindow } from "../utils/pip.js"

const props = defineProps({
	cols: { type: Number, required: true },
	rows: { type: Number, required: true },
	me: { type: Object, default: null },
	others: { type: Array, default: () => [] },
	areas: { type: Array, default: () => [] },
	background: { type: String, default: "" },
	backgroundLayout: { type: Object, default: () => ({ fit: true }) },
	/** [{ id, kind: walkup | message | meeting | reminder, text, user?, fresh? }] */
	pings: { type: Array, default: () => [] },
	noticeCount: { type: Number, default: 0 },
})
const emit = defineEmits(["fullscreen", "reply", "open-chat", "dismiss", "send"])

// Replies typed in a ping: sent by the page (Ophice), which knows the chat behind it.
const drafts = reactive({})
const sending = reactive({})
function reply(ping) {
	const text = (drafts[ping.id] || "").trim()
	if (!text || sending[ping.id]) return
	sending[ping.id] = true
	emit("send", ping, text, (ok) => {
		sending[ping.id] = false
		if (ok) drafts[ping.id] = ""
	})
}

// Served by Frappe, not bundled.
const OPHICE_ICON = "/assets/phamos/manifest/ophice-icon-192.png"
const WIDTH = 280
const MINUTES = [5, 15, 30, 60]
const ICONS = { walkup: "user", message: "message-circle", meeting: "message-square", reminder: "clock" }
const POS_KEY = "phamos_ophice_mini_map_pos"

const tile = computed(() => WIDTH / props.cols)
const mapStyle = computed(() => {
	const layout = props.backgroundLayout || { fit: true }
	return {
		height: `${tile.value * props.rows}px`,
		backgroundColor: "var(--surface-gray-2, #eee)",
		backgroundImage: props.background ? `url("${encodeURI(props.background)}")` : "none",
		backgroundSize: layout.fit ? "cover" : `${layout.scale}% auto`,
		backgroundPosition: layout.fit ? "center" : `${layout.x}% ${layout.y}%`,
		backgroundRepeat: "no-repeat",
	}
})

function areaStyle(area) {
	const t = tile.value
	const h = area.color_hue ?? 220
	return {
		left: `${area.x * t}px`,
		top: `${area.y * t}px`,
		width: `${area.width * t}px`,
		height: `${area.height * t}px`,
		border: `1.5px solid hsl(${h} 70% 45%)`,
		background: `hsl(${h} 70% 45% / 0.25)`,
	}
}

function chipStyle(chip, color) {
	const t = tile.value
	const size = Math.max(7, t * 0.9)
	return {
		width: `${size}px`,
		height: `${size}px`,
		left: `${(chip.x + 0.5) * t - size / 2}px`,
		top: `${(chip.y + 0.5) * t - size / 2}px`,
		background: color,
	}
}

// --- Dragging (place remembered in this browser)

function storedPos() {
	try {
		const pos = JSON.parse(localStorage.getItem(POS_KEY) || "null")
		if (pos && Number.isFinite(pos.x) && Number.isFinite(pos.y)) return pos
	} catch {
		// private window: the default place
	}
	return { x: 16, y: Math.max(16, window.innerHeight - 340) }
}
const pos = reactive(storedPos())
const root = ref(null)
let drag = null

function keepInView() {
	const height = root.value?.offsetHeight || 220
	pos.x = Math.max(4, Math.min(window.innerWidth - WIDTH - 4, pos.x))
	pos.y = Math.max(4, Math.min(window.innerHeight - Math.min(height, 120), pos.y))
}

function startDrag(event) {
	if (floatTarget.value || event.button !== 0) return
	drag = { x: event.clientX - pos.x, y: event.clientY - pos.y }
	window.addEventListener("pointermove", onDrag)
	window.addEventListener("pointerup", endDrag, { once: true })
}
function onDrag(event) {
	if (!drag) return
	pos.x = event.clientX - drag.x
	pos.y = event.clientY - drag.y
	keepInView()
}
function endDrag() {
	drag = null
	window.removeEventListener("pointermove", onDrag)
	try {
		localStorage.setItem(POS_KEY, JSON.stringify({ x: pos.x, y: pos.y }))
	} catch {
		// private window: the place lasts until the reload
	}
}
window.addEventListener("resize", keepInView)
onBeforeUnmount(() => {
	window.removeEventListener("resize", keepInView)
	window.removeEventListener("pointermove", onDrag)
	floatBody?.ownerDocument?.defaultView?.close()
})

// --- Float: Document Picture-in-Picture, a small window on top of everything (Chrome, Edge,
// newer Firefox; not Safari). The same element moves into it; closing it brings it back.

const floatTarget = ref(null)
let floatBody = null

async function float() {
	floatBody = await openFloatingWindow({
		width: WIDTH + 24,
		height: 420,
		onClose: () => {
			floatTarget.value = null
			floatBody = null
		},
	})
	floatTarget.value = floatBody
}
</script>

<style scoped>
.mini-map__chip {
	box-shadow: 0 0 0 1.5px #fff, 0 1px 2px rgba(0, 0, 0, 0.5);
	transition: left 160ms linear, top 160ms linear;
}
.mini-map__chip--me {
	box-shadow: 0 0 0 2px #fff, 0 0 6px 2px rgba(59, 130, 246, 0.8);
	z-index: 1;
}
.mini-map--floating {
	width: 100%;
	min-height: 100vh;
	border-radius: 0;
	border: 0;
}
.mini-map__ping--new {
	animation: mini-map-ping 1.2s ease-out 2;
}
@keyframes mini-map-ping {
	0% { box-shadow: 0 0 0 0 rgba(59, 130, 246, 0.6); }
	100% { box-shadow: 0 0 0 10px rgba(59, 130, 246, 0); }
}
</style>
