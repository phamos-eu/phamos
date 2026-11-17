import { onBeforeUnmount, onMounted, ref } from "vue"
import { CORNERS, GLOW_EDGES, glowSettings, glowStyle, PULSE_MS } from "@spa/utils/cockpitGlow.js"

/**
 * The cockpit's edge glow (#1933): colour and mode come from Cockpit Settings through the boot.
 *
 * Returns null when the glow is off. Otherwise `edges` and `corners` (the pieces to draw),
 * `breathing`, `style` (CSS variables: colour and 1/0 per edge), `steady` (a faint glow all the
 * time), `pulse` (whether it lights up on focus), `frame` (edges and corners of the whole frame,
 * which the focus glow lights before it settles into `edges`) and `pulsing` (a ref, true for
 * PULSE_MS after the window came to the front).
 */
export function useCockpitGlow(cockpitWindow = window.frappe?.boot?.cockpit_window) {
	const settings = glowSettings(cockpitWindow)
	if (!settings) return null

	const pulsing = ref(false)
	let timer = null
	let frame = null

	const cancel = () => {
		clearTimeout(timer)
		cancelAnimationFrame(frame)
	}
	const pulse = () => {
		// focus and visibilitychange often fire together: one glow, no stray timer
		cancel()
		pulsing.value = false
		// Off for a whole frame first, so the browser sees the class removed and a focus during a
		// running glow starts the animation again. One frame is not enough: the class would come
		// back before that frame's style pass (AI review of !1188).
		frame = requestAnimationFrame(() => {
			frame = requestAnimationFrame(() => {
				pulsing.value = true
				timer = setTimeout(() => (pulsing.value = false), PULSE_MS)
			})
		})
	}
	// Alt+Tab / clicking another window fires "focus"; switching browser tabs fires visibilitychange.
	const onVisible = () => document.visibilityState === "visible" && pulse()

	if (settings.pulse) {
		onMounted(() => {
			window.addEventListener("focus", pulse)
			document.addEventListener("visibilitychange", onVisible)
		})
		onBeforeUnmount(() => {
			cancel()
			window.removeEventListener("focus", pulse)
			document.removeEventListener("visibilitychange", onVisible)
		})
	}

	return {
		edges: settings.edges,
		corners: settings.corners,
		breathing: settings.breathing,
		style: glowStyle(settings),
		steady: settings.steady,
		pulse: settings.pulse,
		frame: { edges: GLOW_EDGES, corners: CORNERS.map(([name]) => name) },
		pulsing,
	}
}
