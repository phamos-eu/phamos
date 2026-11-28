// Pure helpers for the event order form's seat reservation (phamos/phamos#1701). No DOM, so they can be
// unit-tested (personal_frontend's vitest run picks up the .test.js next to this file).

/** When the reservation ends, on the visitor's own clock: the server sends how long it lasts, not until when,
 * because the visitor's clock may differ from the server's by minutes. */
export function expiryFromNow(minutes, now = Date.now()) {
	return now + Number(minutes) * 60 * 1000;
}

/** Numbers requests so that only the newest one's answer is used: several reservation requests can be in
 * flight at once (adding, removing, toggling), and an older answer may arrive after a newer one. */
export function createLatest() {
	let latest = 0;
	return {
		next: () => ++latest,
		isLatest: (n) => n === latest,
	};
}
