/**
 * Only pages of this site may open in Ophice's cockpit frame (#2073): "/sales-cockpit/...", never
 * "//other.site" or "/\other.site" (browsers read both as another site). A crafted
 * /ophice/open/... link must not show a foreign page under Ophice's address (review of the release).
 *
 * @param {string} page e.g. "/personal-cockpit/todos?x=1"
 * @param {string} origin the site's origin, e.g. "https://erp.example.com"
 */
export function isOwnPage(page, origin = globalThis.location?.origin) {
	if (typeof page !== "string" || !/^\/[A-Za-z0-9_-]/.test(page) || !origin) return false
	try {
		return new URL(page, origin).origin === origin
	} catch {
		return false
	}
}
