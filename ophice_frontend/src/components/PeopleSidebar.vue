<template>
	<!--
		People (#2063, #2091). Folded: a strip of chips at the side, with status (dot, away / be right
		back), place (the glow of the space) and cockpit (icon) still readable. A click on the strip
		unfolds the full list over the map; the search icon (or Cmd/Ctrl+F) unfolds it with the search
		field focused. It folds back when my chip moves, on a click outside, when the window loses
		focus, or with Esc (PM, 2026-11-22). The handle keeps it open (remembered in this browser).
		In a meeting it shows the people outside the meeting.
	-->
	<div
		ref="root"
		class="relative z-30 h-full flex-shrink-0"
		:class="folded ? 'w-16' : 'w-64'"
		data-testid="people-sidebar"
		:data-folded="folded ? '1' : '0'"
	>
	<aside
		v-if="folded"
		class="flex h-full w-16 cursor-pointer flex-col items-center gap-2 overflow-y-auto border-r border-outline-gray-2 bg-surface-white py-2"
		:aria-label="__('People')"
		:title="__('Open the people list')"
		data-testid="people-strip"
		@click="unfold()"
	>
		<button
			type="button"
			class="flex flex-col items-center rounded-lg px-1.5 py-1 text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-9"
			:title="__('Find a person ({0})', [findShortcut])"
			data-testid="people-search-open"
			@click.stop="openSearch()"
		>
			<FeatherIcon name="search" class="h-4 w-4" />
		</button>
		<span class="flex flex-col items-center text-[10px] tabular-nums text-ink-gray-5" :title="__('{0} online', [onlineCount])">
			<FeatherIcon name="users" class="h-3.5 w-3.5" />{{ onlineCount }}
		</span>
		<!-- A click on a chip opens the list too: from there a click starts a chat. -->
		<div
			v-for="person in stripPeople"
			:key="person.user"
			class="relative flex-shrink-0 rounded-full"
			:class="{ 'opacity-50': !person.online }"
			:title="`${person.full_name} · ${lineOf(person).text}`"
			data-testid="person"
		>
			<span class="block rounded-full" :style="chipStyle(person)">
				<UserAvatar :name="person.user" :label="person.full_name" :image="person.user_image" size="sm" />
			</span>
			<span class="absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full border-2 border-surface-white" :class="dotClass(person)" />
			<!-- Away / be right back at a glance -->
			<span
				v-if="person.status?.kind === 'away' || person.status?.kind === 'brb'"
				class="absolute -left-1.5 -top-1.5 flex h-4 w-4 items-center justify-center rounded-full bg-surface-white text-ink-gray-7 shadow"
				data-testid="person-status-badge"
			>
				<FeatherIcon :name="person.status.kind === 'away' ? 'moon' : 'coffee'" class="h-2.5 w-2.5" />
			</span>
			<!-- The cockpit they work in (#2065) -->
			<img
				v-if="person.online && person.cockpit?.logo"
				:src="person.cockpit.logo"
				alt=""
				class="absolute -bottom-1 -left-1 h-3.5 w-3.5 rounded ring-2 ring-surface-white"
				data-testid="person-cockpit-badge"
			/>
		</div>
	</aside>
	<!-- The full list: in the page when kept open, over the map while the strip is hovered. -->
	<aside
		v-if="!folded || unfolded"
		class="flex w-64 flex-col border-r border-outline-gray-2 bg-surface-white text-ink-gray-9"
		:class="folded ? 'people--over absolute inset-y-0 left-0 z-40 shadow-2xl' : 'h-full'"
		:aria-label="__('People')"
		data-testid="people-list"
	>
		<div class="flex items-center gap-2 px-3 pb-2 pt-3">
			<span class="text-sm font-semibold">{{ __("People") }}</span>
			<span class="text-xs text-ink-gray-5">{{ __("{0} online", [onlineCount]) }}</span>
			<button
				v-if="!meeting"
				type="button"
				class="ml-auto rounded p-1 text-ink-gray-5 hover:bg-surface-gray-2 hover:text-ink-gray-9"
				:title="pinned ? __('Fold the list back to the chips') : __('Keep the people list open')"
				data-testid="people-fold"
				@click="$emit('pin', !pinned)"
			>
				<FeatherIcon :name="pinned ? 'chevrons-left' : 'chevrons-right'" class="h-4 w-4" />
			</button>
		</div>
		<div class="px-3 pb-2">
			<input
				ref="search"
				v-model="query"
				type="search"
				class="form-input h-7 w-full rounded border-outline-gray-2 bg-surface-gray-2 px-2 text-xs text-ink-gray-9"
				:placeholder="__('Find a person')"
				data-testid="people-search"
				@keydown.esc.stop.prevent="query ? (query = '') : fold()"
			/>
		</div>
		<ul class="min-h-0 flex-1 overflow-y-auto px-1.5 pb-2">
			<li v-for="person in shown" :key="person.user">
				<button
					type="button"
					class="flex w-full items-center gap-2.5 rounded-lg px-1.5 py-1.5 text-left hover:bg-surface-gray-2"
					:class="{ 'opacity-60': !person.online }"
					:disabled="person.user === me"
					data-testid="person"
					@click="$emit('pick', person, $event)"
				>
					<span class="relative flex-shrink-0">
						<span
							class="block rounded-full"
							:style="chipStyle(person)"
						>
							<UserAvatar :name="person.user" :label="person.full_name" :image="person.user_image" size="sm" />
						</span>
						<span
							class="absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full border-2 border-surface-white"
							:class="dotClass(person)"
						/>
					</span>
					<span class="min-w-0 flex-1">
						<span class="flex items-center gap-1 text-sm">
							<span class="truncate">
								{{ person.full_name }}<span v-if="person.user === me" class="text-ink-gray-5"> ({{ __("you") }})</span>
							</span>
							<!-- An external guest (#2082) -->
							<span
								v-if="person.guest"
								class="flex-shrink-0 rounded-full bg-amber-600 px-1.5 text-[10px] font-semibold leading-4 text-white"
								data-testid="person-guest"
							>
								{{ __("Guest") }}
							</span>
							<!-- The cockpit they are in right now (#2065). -->
							<img
								v-if="person.cockpit?.logo"
								:src="person.cockpit.logo"
								:alt="person.cockpit.title"
								:title="__('In {0}', [person.cockpit.title])"
								class="h-4 w-4 flex-shrink-0 rounded"
								data-testid="person-cockpit"
							/>
						</span>
						<span class="flex items-center gap-1 truncate text-xs text-ink-gray-5">
							<FeatherIcon v-if="lineOf(person).icon" :name="lineOf(person).icon" class="h-3 w-3 flex-shrink-0" />
							<span class="truncate">{{ lineOf(person).text }}</span>
						</span>
					</span>
				</button>
				<WorkingOnCard v-if="person.working_on" :card="person.working_on" class="mb-1 ml-11 mr-1.5" />
			</li>
		</ul>
		<!-- Cockpit spaces (#2076) -->
		<label class="flex cursor-pointer items-start gap-2 border-t border-outline-gray-2 px-3 py-2 text-xs text-ink-gray-6">
			<input
				type="checkbox"
				class="mt-0.5 rounded"
				:checked="autoCockpit"
				data-testid="auto-cockpit"
				@change="$emit('auto-cockpit', $event.target.checked)"
			/>
			<span>
				<span class="font-medium text-ink-gray-8">{{ __("Open cockpits in their spaces") }}</span><br />
				{{ __("Stopping in a cockpit space opens that cockpit.") }}
			</span>
		</label>
		<label class="flex cursor-pointer items-start gap-2 border-t border-outline-gray-2 px-3 py-2 text-xs text-ink-gray-6">
			<input
				type="checkbox"
				class="mt-0.5 rounded"
				:checked="hideDetails"
				data-testid="hide-details"
				@change="$emit('hide', $event.target.checked)"
			/>
			<span>
				<span class="font-medium text-ink-gray-8">{{ __("Hide my details") }}</span><br />
				{{ __("Others then only see that you are online, not where or on what.") }}
			</span>
		</label>
	</aside>
	</div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue"
import { FeatherIcon } from "frappe-ui"
import UserAvatar from "@spa/components/UserAvatar.vue"
import WorkingOnCard from "./WorkingOnCard.vue"
import { __ } from "@spa/utils/i18n.js"
import { clockTime } from "../utils/ophiceTime.js"
import { ringHue } from "../utils/ophiceColor.js"

const props = defineProps({
	people: { type: Array, default: () => [] },
	me: { type: String, default: "" },
	hideDetails: { type: Boolean, default: false },
	/** Date.now(), ticking */
	now: { type: Number, default: () => Date.now() },
	/** The area I'm meeting in (collapses the list to chips), or null. */
	meeting: { type: Object, default: null },
	/** user → the area their chip stands in, from the map */
	areaOf: { type: Object, default: () => ({}) },
	/** Cockpit spaces open their cockpit when I stop inside (#2076). */
	autoCockpit: { type: Boolean, default: true },
	/** Kept open; otherwise folded to the chips, unfolding on hover (#2091). */
	pinned: { type: Boolean, default: false },
})
defineEmits(["pick", "hide", "auto-cockpit", "pin"])

// Folded: the strip of chips; in a meeting always (the people there huddle above the chat).
const folded = computed(() => Boolean(props.meeting) || !props.pinned)
const stripPeople = computed(() => (props.meeting ? outside.value : props.people))
// Unfolded over the map by a click, the search icon or Cmd/Ctrl+F (#2091).
const unfolded = ref(false)
const root = ref(null)
const search = ref(null)
const findShortcut = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent) ? "⌘ F" : "Ctrl + F"

function unfold() {
	if (folded.value) unfolded.value = true
}
/** Open the list with the search field focused (search icon, Cmd/Ctrl+F). */
function openSearch() {
	unfolded.value = true
	nextTick(() => {
		search.value?.focus()
		search.value?.select()
	})
}
/** Fold back to the strip: my chip moved, a click outside, the window lost focus, Esc. */
function fold() {
	if (!unfolded.value) return
	unfolded.value = false
	query.value = ""
	search.value?.blur()
}
function onPointerDownOutside(event) {
	if (unfolded.value && root.value && !root.value.contains(event.target)) fold()
}
onMounted(() => {
	document.addEventListener("pointerdown", onPointerDownOutside, true)
	window.addEventListener("blur", fold)
})
onBeforeUnmount(() => {
	document.removeEventListener("pointerdown", onPointerDownOutside, true)
	window.removeEventListener("blur", fold)
})

defineExpose({ openSearch, fold })

const query = ref("")
const onlineCount = computed(() => props.people.filter((p) => p.online).length)
const shown = computed(() => {
	const q = query.value.trim().toLowerCase()
	if (!q) return props.people
	return props.people.filter((p) => `${p.full_name} ${p.user}`.toLowerCase().includes(q))
})

const inMeeting = computed(() => {
	const name = props.meeting?.name
	const here = props.people.filter((p) => p.online && props.areaOf[p.user]?.name === name)
	return here
})
const outside = computed(() => {
	const here = new Set(inMeeting.value.map((p) => p.user))
	return props.people.filter((p) => !here.has(p.user))
})

/** The person's ring; when they stand in a meeting area, a glow in its colour around it. */
function chipStyle(person) {
	const ring = person.user === props.me ? "rgb(37,99,235)" : `hsl(${ringHue(person.user)} 80% 45%)`
	const area = person.online ? props.areaOf[person.user] : null
	if (!area) return { boxShadow: `0 0 0 2px ${ring}` }
	const glow = `hsl(${area.color_hue} 75% 50%)`
	return { boxShadow: `0 0 0 2px ${ring}, 0 0 0 4px var(--surface-white, #fff), 0 0 0 6px ${glow}, 0 0 10px 4px hsl(${area.color_hue} 75% 50% / 0.55)` }
}

function dotClass(person) {
	if (person.status?.kind === "away") return "bg-surface-gray-5"
	if (person.status?.kind === "brb") return "bg-amber-500"
	return person.online ? "bg-green-500" : "bg-surface-gray-4"
}

/** One line: their own status first, then where they are, as far as they show it. */
function lineOf(person) {
	const status = person.status
	if (status?.kind === "away") {
		const back = status.until ? clockTime(new Date(status.until), new Date(props.now)) : ""
		return { icon: "moon", text: [__("Away"), back && __("back {0}", [back]), status.note].filter(Boolean).join(" · ") }
	}
	if (!person.online) return { icon: "", text: __("Not in Ophice") }
	if (status?.kind === "brb") return { icon: "coffee", text: [__("Be right back"), status.note].filter(Boolean).join(" · ") }
	if (person.hidden && person.user !== props.me) return { icon: "", text: __("Online") }
	if (person.in_chat) return { icon: "message-circle", text: __("In a chat") }
	if (person.area) return { icon: "video", text: __("In {0}", [person.area]) }
	return { icon: "", text: __("Around in Ophice") }
}
</script>

<style scoped>
.people--over {
	animation: people-unfold 140ms ease-out;
}
@keyframes people-unfold {
	from {
		opacity: 0;
		transform: translateX(-12px);
	}
}
@media (prefers-reduced-motion: reduce) {
	.people--over {
		animation: none;
	}
}
</style>
