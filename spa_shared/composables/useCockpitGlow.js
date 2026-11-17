import { onBeforeUnmount, onMounted, ref } from "vue"
import { glowSettings, glowStyle, PULSE_MS } from "@spa/utils/cockpitGlow.js"

/**
 * The cockpit's edge glow (#1933): colour and mode come from Cockpit Settings through the boot.
 *
 * Returns null when the glow is off. Otherwise `style` (CSS variables: colour and edges),
 * `steady` (a faint glow all the time) and `pulsing` (a ref, true for PULSE_MS after the window
 * came to the front).
 */
export function useCockpitGlow(cockpitWindow = window.frappe?.boot?.cockpit_window) {
	const settings = glowSettings(cockpitWindow)
	if (!settings) return null

	const pulsing = ref(false)
	let timer = null

	const pulse = () => {
		clearTimeout(timer)
		pulsing.value = true
		timer = setTimeout(() => (pulsing.value = false), PULSE_MS)
	}
	// Alt+Tab / clicking another window fires "focus"; switching browser tabs fires visibilitychange.
	const onVisible = () => document.visibilityState === "visible" && pulse()

	if (settings.pulse) {
		onMounted(() => {
			window.addEventListener("focus", pulse)
			document.addEventListener("visibilitychange", onVisible)
		})
		onBeforeUnmount(() => {
			clearTimeout(timer)
			window.removeEventListener("focus", pulse)
			document.removeEventListener("visibilitychange", onVisible)
		})
	}

	return { style: glowStyle(settings), steady: settings.steady, pulsing }
}
