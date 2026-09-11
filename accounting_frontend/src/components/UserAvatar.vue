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
			:class="[abbrSizeClass, `avatar-desk-${palette.key}`]"
			:title="title"
		>
			{{ abbr }}
		</span>
	</span>
</template>

<script setup>
import { computed } from "vue"
import { getAvatarAbbr, getAvatarPalette } from "../avatar.js"

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
const image = computed(() => (props.image || "").trim() || "")
</script>

<style>
/* Light mode: stronger than Desk 50/100 tokens so initials read on white SPA surfaces */
.avatar-desk-orange {
	background-color: #f7d6bd;
	color: #bd3e0c;
}
.avatar-desk-pink {
	background-color: #f8e2f0;
	color: #9c2671;
}
.avatar-desk-blue {
	background-color: #c9e7fc;
	color: #0070cc;
}
.avatar-desk-green,
.avatar-desk-dark-green {
	background-color: #cae5d4;
	color: #16794c;
}
.avatar-desk-red {
	background-color: #fcd7d7;
	color: #b52a2a;
}
.avatar-desk-yellow {
	background-color: #f7e9a8;
	color: #ab6e05;
}
.avatar-desk-purple {
	background-color: #f1e5fa;
	color: #6e399d;
}

:root[data-theme="dark"] .avatar-desk-orange {
	background-color: #d45a08;
	color: #fff1e7;
}
:root[data-theme="dark"] .avatar-desk-pink {
	background-color: #e34aa6;
	color: #fff7fc;
}
:root[data-theme="dark"] .avatar-desk-blue {
	background-color: #0289f7;
	color: #f7fbfd;
}
:root[data-theme="dark"] .avatar-desk-green,
:root[data-theme="dark"] .avatar-desk-dark-green {
	background-color: #16794c;
	color: #daf0e1;
}
:root[data-theme="dark"] .avatar-desk-red {
	background-color: #e03636;
	color: #fff7f7;
}
:root[data-theme="dark"] .avatar-desk-yellow {
	background-color: #edba13;
	color: #fffcef;
}
:root[data-theme="dark"] .avatar-desk-purple {
	background-color: #9c45e3;
	color: #fdfaff;
}
</style>
