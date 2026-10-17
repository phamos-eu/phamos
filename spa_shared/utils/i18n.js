// Translations for the cockpit SPAs (#1605), the same way Desk does it: the page boots with the
// user's language and its translation table (phamos/www/spa_boot.py), and __() looks strings up.
// Same name and "{0}" placeholders as Frappe's __(), so `bench get-untranslated` finds them and
// translations live in the apps' translations/<lang>.csv files.

function table() {
	return (typeof window !== "undefined" && window.frappe?.boot?.__messages) || {}
}

/**
 * Translate `text` and fill "{0}", "{1}" … with `replace`. Unknown text comes back unchanged.
 * @param {string} text English source text
 * @param {Array} [replace] values for the placeholders
 */
export function __(text, replace) {
	let message = table()[text] || text
	if (replace && replace.length) {
		message = message.replace(/\{(\d+)\}/g, (match, index) => (replace[index] !== undefined ? replace[index] : match))
	}
	return message
}

/** Vue plugin: makes __() available in templates. */
export const i18n = {
	install(app) {
		app.config.globalProperties.__ = __
	},
}
