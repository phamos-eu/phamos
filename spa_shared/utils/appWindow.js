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
 * Open another cockpit. In an installed app it opens outside this window (in that cockpit's own
 * app when it is installed), so this cockpit's window stays what it is; in a browser tab it
 * navigates.
 *
 * @param {string} route the cockpit's route, e.g. "/team-cockpit"
 */
export function openCockpit(route) {
	if (isInstalledApp()) {
		window.open(route, "_blank", "noopener")
		return
	}
	window.location.href = route
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
