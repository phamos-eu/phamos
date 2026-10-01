/**
 * Helpers for cockpits running as installed desktop apps (#1458).
 *
 * Each cockpit is its own installable app (see phamos/public/manifest/*.webmanifest),
 * so users can cmd+tab between them. Leaving the cockpit for Desk must not turn the
 * cockpit window into Desk, or the user loses that window in the app switcher.
 */

/** True when the page runs in an installed app window rather than a browser tab. */
export function isInstalledApp() {
	return window.matchMedia("(display-mode: standalone)").matches
}

/**
 * Open a Desk URL. In an installed app it opens in the browser and the cockpit window
 * stays as it is; in a browser tab it navigates as before.
 *
 * @param {string} [path="/app"] Desk URL to open
 */
export function openDesk(path = "/app") {
	if (isInstalledApp()) {
		window.open(path, "_blank", "noopener")
		return
	}
	window.location.href = path
}
