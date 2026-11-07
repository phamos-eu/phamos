// Privacy mode for screen sharing (#1839). Sensitive figures are blurred until someone clicks
// "Show data"; then they stay visible for a set time and blur again by themselves. Clicking the
// countdown starts the time again, so people allowed to see the data aren't interrupted.
//
// One state per browser tab, shared by every component that imports this module. It always
// starts hidden, so a reload or a new tab never shows data. It is a visual guard for a shared
// screen, not an access rule: what a role may read is decided by the API.

import { computed, ref } from "vue"

const enabled = ref(false)
const revealSeconds = ref(120)
const deadline = ref(0)
const now = ref(Date.now())
let ticker = null

function stopTicker() {
	if (ticker) clearInterval(ticker)
	ticker = null
}

function tick() {
	now.value = Date.now()
	// Measured against the clock, not counted down, so a throttled background tab still hides on time.
	if (now.value >= deadline.value) hide()
}

/** Show the data for the configured time, or start that time again while it shows. */
function reveal() {
	deadline.value = Date.now() + revealSeconds.value * 1000
	now.value = Date.now()
	if (!ticker) ticker = setInterval(tick, 250)
}

function hide() {
	deadline.value = 0
	stopTicker()
}

/** Turn privacy mode on for this cockpit; `seconds` comes from Phamos Settings. */
export function enablePrivacyMode(seconds) {
	if (Number(seconds) > 0) revealSeconds.value = Number(seconds)
	enabled.value = true
}

const visible = computed(() => deadline.value > now.value)
const hidden = computed(() => enabled.value && !visible.value)
const secondsLeft = computed(() => (visible.value ? Math.ceil((deadline.value - now.value) / 1000) : 0))

export function usePrivacyMode() {
	return { enabled, hidden, secondsLeft, revealSeconds, reveal, extend: reveal, hide }
}
