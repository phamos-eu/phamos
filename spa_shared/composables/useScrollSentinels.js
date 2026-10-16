// Calls onTop / onBottom when sentinel elements near the start or end of a scroll container come
// into view (infinite scrolling in both directions). Must be called during component setup.
import { onBeforeUnmount, onMounted } from "vue"

export function useScrollSentinels(rootRef, topRef, bottomRef, { onTop, onBottom, margin = "400px" } = {}) {
	let observer = null
	onMounted(() => {
		if (typeof IntersectionObserver === "undefined") return
		observer = new IntersectionObserver(
			(entries) => {
				for (const entry of entries) {
					if (!entry.isIntersecting) continue
					if (entry.target === topRef.value) onTop?.()
					if (entry.target === bottomRef.value) onBottom?.()
				}
			},
			{ root: rootRef.value, rootMargin: `${margin} 0px ${margin} 0px` }
		)
		if (topRef.value) observer.observe(topRef.value)
		if (bottomRef.value) observer.observe(bottomRef.value)
	})
	onBeforeUnmount(() => observer?.disconnect())
	// Re-check both ends, e.g. after content changed but the sentinels stayed in view.
	return {
		recheck() {
			if (!observer) return
			for (const el of [topRef.value, bottomRef.value]) {
				if (!el) continue
				observer.unobserve(el)
				observer.observe(el)
			}
		},
	}
}
