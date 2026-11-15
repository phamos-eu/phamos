// The user's image size in the cockpits' rich text (#1918): small, medium or large, shared by every
// field on the page, booted with it (spa_boot → preferences.cockpit_image_size) and saved as a
// user default. It only changes how this user sees images; the text keeps their stored widths.

import { ref } from "vue"
import { call } from "frappe-ui"
import { normalizeImageSize } from "@spa/utils/imageSize.js"

const KEY = "cockpit_image_size"
const booted = typeof window !== "undefined" ? window.frappe?.boot?.preferences?.[KEY] : null
const size = ref(normalizeImageSize(booted))

async function setImageSize(value) {
	const next = normalizeImageSize(value)
	if (next === size.value) return
	size.value = next
	try {
		await call("phamos.api.cockpit_preferences.set_preference", { key: KEY, value: JSON.stringify(next) })
	} catch (e) {
		// a view setting: the page keeps working with the unsaved one
		console.warn("Could not save the image size", e)
	}
}

export function useImageSize() {
	return { imageSize: size, setImageSize }
}
