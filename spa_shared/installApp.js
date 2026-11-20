import { reactive } from "vue"
import { isInstalledApp } from "@spa/utils/appWindow.js"

/**
 * Shared state of the install hint (#1998): CockpitShell shows the dialog, the sidebar's
 * "Install as app" entry opens it.
 *
 * Chromium fires `beforeinstallprompt` once, often before Vue has mounted anything, and the
 * event is the only way to offer a real "Install" button. So this module listens as soon as it
 * is imported: CockpitShell imports it, App.vue imports CockpitShell, and main.js imports App.vue
 * statically, so the listener exists before the app mounts.
 */
export const installApp = reactive({
	/** The deferred `beforeinstallprompt` event; null in Safari, Firefox or when installed. */
	prompt: null,
	/** Installed during this visit (the `appinstalled` event). */
	installed: false,
	/** The dialog is open. */
	open: false,
})

if (typeof window !== "undefined") {
	window.addEventListener("beforeinstallprompt", (event) => {
		// Keep the browser's own mini-infobar away; our dialog offers the button instead.
		event.preventDefault()
		installApp.prompt = event
	})
	window.addEventListener("appinstalled", () => {
		installApp.installed = true
		installApp.prompt = null
	})
}

/** True when an "Install as app" offer makes sense on this page. */
export function canOfferInstall() {
	return !installApp.installed && !isInstalledApp()
}

export function openInstallHint() {
	installApp.open = true
}
