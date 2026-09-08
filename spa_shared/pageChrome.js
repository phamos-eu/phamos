import { reactive } from "vue"

/** Optional override for CockpitShell header (e.g. open Issue subject + id). */
export const pageChrome = reactive({
	active: false,
})

export function setPageChromeActive(active) {
	pageChrome.active = !!active
}
