<template>
	<span
		class="avatar inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full"
		:class="sizeClass"
		:title="title"
	>
		<span
			v-if="image"
			class="avatar-frame block h-full w-full rounded-full bg-cover bg-center bg-no-repeat"
			:style="{ backgroundImage: `url('${image}')` }"
			:title="title"
		/>
		<span
			v-else
			class="avatar-frame standard-image flex h-full w-full items-center justify-center rounded-full font-normal uppercase"
			:class="abbrSizeClass"
			:style="paletteStyle"
			:title="title"
		>
			{{ abbr }}
		</span>
	</span>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue"
import { getAvatarAbbr, getAvatarPalette } from "@spa/utils/avatar.js"

const props = defineProps({
	/** User id / email (optional; used for title fallback) */
	name: { type: String, default: "" },
	/** Display name used for initials + palette (must match list + detail) */
	label: { type: String, default: "" },
	image: { type: String, default: "" },
	/** Desk list uses avatar-small (28px) */
	size: {
		type: String,
		default: "sm",
		validator: (v) => ["xs", "sm", "md"].includes(v),
	},
})

/** Same seed as Desk: fullname / label, then user id. */
const title = computed(() => (props.label || props.name || "").trim() || "?")

const sizeClass = computed(() => {
	const map = {
		xs: "h-4 w-4",
		sm: "h-7 w-7",
		md: "h-8 w-8",
	}
	return map[props.size]
})

const abbrSizeClass = computed(() => {
	const map = {
		xs: "text-[9px]",
		sm: "text-xs",
		md: "text-sm",
	}
	return map[props.size]
})

const abbr = computed(() => {
	const max = props.size === "xs" || props.size === "sm" ? 1 : 2
	return getAvatarAbbr(title.value, max)
})

const palette = computed(() => getAvatarPalette(title.value))

const isDark = ref(false)

function syncDark() {
	isDark.value = document.documentElement.dataset.theme === "dark"
}

let themeObserver
onMounted(() => {
	syncDark()
	themeObserver = new MutationObserver(syncDark)
	themeObserver.observe(document.documentElement, {
		attributes: true,
		attributeFilter: ["data-theme"],
	})
})
onUnmounted(() => themeObserver?.disconnect())

const paletteStyle = computed(() => {
	const p = palette.value
	if (isDark.value) {
		return { backgroundColor: p.darkBg, color: p.darkColor }
	}
	return { backgroundColor: p.bg, color: p.color }
})

const image = computed(() => (props.image || "").trim() || "")
</script>
