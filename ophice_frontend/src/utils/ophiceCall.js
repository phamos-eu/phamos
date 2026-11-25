// A Jitsi call in its own browser window: encounter calls and meeting areas (#2108, #2078).

/**
 * Address of the call page: the room on its Jitsi host, with my name filled in.
 * @param {{ domain: string, room: string }} video  the call: an encounter's (open_encounter) or an area's
 * @param {string} displayName  my name in the call
 * @returns {string} the URL, or "" without a call
 */
export function jitsiCallUrl(video, displayName = "") {
	const domain = String(video?.domain || "").trim().replace(/^https?:\/\//, "").replace(/\/+$/, "")
	const room = String(video?.room || "").trim()
	if (!domain || !room || /[/\\?#@\s]/.test(domain)) return ""
	// Jitsi reads settings from the fragment as JSON values; the fragment never reaches a server.
	// Whoever opens the call wants to talk: mic and camera on, straight in without the pre-join
	// screen (#2108). The browser still asks once for the permission to use them.
	const settings = [
		"config.startWithAudioMuted=false",
		"config.startWithVideoMuted=false",
		"config.prejoinConfig.enabled=false",
		"config.prejoinPageEnabled=false",
	]
	if (displayName) settings.push(`userInfo.displayName=${encodeURIComponent(JSON.stringify(displayName))}`)
	return `https://${domain}/${encodeURIComponent(room)}#${settings.join("&")}`
}

/** Window name of the call: opening it again brings the same window back. */
export function encounterCallWindowName(video) {
	return `ophice-call-${String(video?.room || "").replace(/[^A-Za-z0-9_-]/g, "")}`
}
