// Image sizes in the cockpits' rich text (#1918). Pure, so it can be tested without a browser.

/** The per-user view setting: how wide images may show in rich text fields. */
export const IMAGE_SIZES = ["small", "medium", "large"]
export const DEFAULT_IMAGE_SIZE = "large"
/** max-width per setting, in px; large is only capped by the field. */
export const IMAGE_SIZE_CAP = { small: 200, medium: 400, large: null }

export const MIN_IMAGE_WIDTH = 40

/**
 * The width stored on an <img>, in px, or null: the `width` attribute (cockpit, Desk) or an inline
 * `style="width: …px"` (Desk's image resize). Percentages and other units are left alone.
 */
export function parseImageWidth({ widthAttr, styleWidth } = {}) {
	for (const raw of [widthAttr, styleWidth]) {
		const m = /^\s*(\d+(?:\.\d+)?)\s*(px)?\s*$/.exec(raw || "")
		if (m) return Math.round(Number(m[1]))
	}
	return null
}

/** A dragged width, kept between MIN_IMAGE_WIDTH and the room the field has. */
export function clampImageWidth(width, max) {
	const top = Math.max(MIN_IMAGE_WIDTH, Math.floor(max || Infinity))
	return Math.round(Math.min(Math.max(width, MIN_IMAGE_WIDTH), top))
}

export function normalizeImageSize(value) {
	return IMAGE_SIZES.includes(value) ? value : DEFAULT_IMAGE_SIZE
}
