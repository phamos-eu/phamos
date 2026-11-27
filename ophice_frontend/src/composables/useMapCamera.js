// The camera over an Ophice map (#2089): zoom, pan by drag or scroll with a bounce at the edges,
// and following my chip. Used by the big map, the meeting view's mini map and the cockpit mini map.
//
// `pan` is where the map's top left corner sits in the view (px). The map ("canvas") is the grid
// and the background image together; the grid's tile (0,0) sits at `origin` inside it.
import { computed, reactive, ref, watch } from "vue"
import {
	canvasRect,
	clamp,
	clampZoom,
	fitTile,
	follow,
	panBounds,
	rubber,
	zoomAround,
} from "../utils/ophiceView.js"

const DRAG_THRESHOLD = 4
const WHEEL_SETTLE_MS = 150
const FOLLOW_SHARE = 0.2

function prefersReducedMotion() {
	return typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
}

/**
 * @param {object} options
 * @param {{width:number,height:number}|(() => {width:number,height:number})} options.view  the view's size
 * @param {() => {cols:number, rows:number}} options.grid
 * @param {() => {left,top,width,height}|null} options.image  where the background lies, in tiles
 * @param {string} options.storageKey  this browser remembers the zoom under it
 * @param {() => number} [options.startZoom]  the map editor's starting zoom, when nothing is stored
 * @param {number} [options.pad]  room around the map (px)
 * @param {number} [options.minTile]
 * @param {boolean} [options.overscroll]  the view may go past the map's edges, up to half its size,
 *   so any point (my chip) can sit in the middle (the mini map, #2155)
 */
export function useMapCamera({ view: viewSource, grid, image, storageKey, startZoom = () => 1, pad = 16, minTile = 4, overscroll = false }) {
	// The view's size: a reactive object, or a function returning one (a derived size).
	const view = {
		get width() {
			return (typeof viewSource === "function" ? viewSource() : viewSource)?.width || 0
		},
		get height() {
			return (typeof viewSource === "function" ? viewSource() : viewSource)?.height || 0
		},
	}
	const zoom = ref(stored() ?? clampZoom(startZoom()))
	const pan = reactive({ x: 0, y: 0 })
	// Past the edge (the bounce), on top of the clamped pan.
	const over = reactive({ x: 0, y: 0 })
	// Springs back with an eased transition (drag ended, wheel settled).
	const springing = ref(false)
	// A hand pan looks around freely; my next step brings the view back to my chip.
	const followPaused = ref(false)
	const dragging = ref(false)
	let placed = false

	function stored() {
		try {
			const value = parseFloat(localStorage.getItem(storageKey))
			return Number.isFinite(value) ? clampZoom(value) : null
		} catch {
			return null
		}
	}
	function remember() {
		try {
			localStorage.setItem(storageKey, String(zoom.value))
		} catch {
			// private window: the zoom lasts until the reload
		}
	}

	const baseTile = computed(() => {
		const { cols, rows } = grid()
		return fitTile(view.width, view.height, cols, rows, pad, minTile)
	})
	const tile = computed(() => (baseTile.value ? Math.max(minTile, Math.round(baseTile.value * zoom.value * 100) / 100) : 0))
	const canvas = computed(() => {
		const { cols, rows } = grid()
		return canvasRect(cols, rows, image())
	})
	const size = computed(() => ({ width: canvas.value.w * tile.value, height: canvas.value.h * tile.value }))
	const origin = computed(() => ({ x: -canvas.value.x * tile.value, y: -canvas.value.y * tile.value }))
	const bounds = computed(() =>
		overscroll
			? {
					x: { min: view.width / 2 - size.value.width, max: view.width / 2 },
					y: { min: view.height / 2 - size.value.height, max: view.height / 2 },
				}
			: { x: panBounds(view.width, size.value.width, pad), y: panBounds(view.height, size.value.height, pad) }
	)
	const transform = computed(() => `translate3d(${pan.x + over.x}px, ${pan.y + over.y}px, 0)`)

	function clampPan() {
		pan.x = clamp(pan.x, bounds.value.x)
		pan.y = clamp(pan.y, bounds.value.y)
	}

	/** Put the grid point (tiles) in the middle of the view. */
	function centerOn(x, y) {
		pan.x = view.width / 2 - (x - canvas.value.x) * tile.value
		pan.y = view.height / 2 - (y - canvas.value.y) * tile.value
		clampPan()
	}

	/** The view px of a grid point (tiles). */
	function toView(x, y) {
		return { x: pan.x + origin.value.x + x * tile.value, y: pan.y + origin.value.y + y * tile.value }
	}

	function setZoom(value, point = { x: view.width / 2, y: view.height / 2 }) {
		const next = clampZoom(value)
		if (next === zoom.value || !tile.value) {
			zoom.value = next
			remember()
			return
		}
		const oldTile = tile.value
		zoom.value = next
		remember()
		const newTile = tile.value
		pan.x = zoomAround(pan.x, oldTile, newTile, point.x)
		pan.y = zoomAround(pan.y, oldTile, newTile, point.y)
		clampPan()
	}

	function zoomBy(factor, point) {
		setZoom(Math.round(zoom.value * factor * 100) / 100, point)
	}

	function springBack() {
		if (!over.x && !over.y) return
		springing.value = true
		over.x = 0
		over.y = 0
		setTimeout(() => (springing.value = false), 420)
	}

	/** Move by (dx, dy) px; past the edge with resistance (the bounce). */
	function panBy(dx, dy, base = { x: pan.x + over.x, y: pan.y + over.y }) {
		const raw = { x: base.x + dx, y: base.y + dy }
		pan.x = clamp(raw.x, bounds.value.x)
		pan.y = clamp(raw.y, bounds.value.y)
		const elastic = !prefersReducedMotion()
		over.x = elastic ? rubber(raw.x - pan.x) : 0
		over.y = elastic ? rubber(raw.y - pan.y) : 0
	}

	// --- Drag to pan with one finger (or the mouse); pinch with two to zoom (#2213). A press that
	// moves less than a few px stays a click (chips, spaces).
	// The fingers on the map, by pointer id: where each is now (client px).
	const pointers = new Map()
	let start = null
	let pinch = null
	let suppressClick = false

	function capture(target, id) {
		try {
			target?.setPointerCapture?.(id)
		} catch {
			// the gesture still works while the pointers stay over the map
		}
	}

	/** Start (or restart) a one-finger drag from where this pointer is now. */
	function startDrag(id, target) {
		const at = pointers.get(id)
		start = { x: at.x, y: at.y, panX: pan.x + over.x, panY: pan.y + over.y, id, target }
	}

	/** Distance and middle (view px) of two fingers. */
	function twoFingers(box, ids) {
		const [a, b] = ids.map((id) => pointers.get(id))
		return {
			dist: Math.hypot(b.x - a.x, b.y - a.y),
			mid: { x: (a.x + b.x) / 2 - box.left, y: (a.y + b.y) / 2 - box.top },
		}
	}

	/**
	 * @param {PointerEvent} event
	 * @param {{pan?: boolean}} [options]  pan: false only notes the finger (it landed on a chip), so
	 *   a second finger can pinch with it; alone it does not move the map and its tap stays a click.
	 */
	function onPointerDown(event, { pan: pans = true } = {}) {
		if (event.button !== 0) return
		// Only fingers pinch. A mouse released outside the map, or a touch that ended without a
		// pointerup or pointercancel, left an entry behind: the first finger down starts fresh.
		if (event.pointerType !== "touch" || event.isPrimary) {
			pointers.clear()
			pinch = null
			start = null
		}
		pointers.set(event.pointerId, { x: event.clientX, y: event.clientY })
		if (pointers.size === 1) {
			if (pans) startDrag(event.pointerId, event.currentTarget)
			return
		}
		if (pointers.size !== 2 || pinch) return
		// The second finger: a pinch. Zoom follows the distance between the two, pan their middle.
		// A third finger is ignored.
		const ids = [...pointers.keys()]
		const target = start?.target || event.currentTarget
		const box = target?.getBoundingClientRect?.() || { left: 0, top: 0 }
		const { dist, mid } = twoFingers(box, ids)
		if (!dist) return
		pinch = { ids, dist, zoom: zoom.value, mid, box, target }
		start = null
		dragging.value = true
		springing.value = false
		followPaused.value = true
		for (const id of pointers.keys()) capture(target, id)
	}

	function onPointerMove(event) {
		const at = pointers.get(event.pointerId)
		if (!at) return
		at.x = event.clientX
		at.y = event.clientY
		if (pinch) {
			if (!pinch.ids.includes(event.pointerId)) return
			const { dist, mid } = twoFingers(pinch.box, pinch.ids)
			// The map under the fingers moves with them, then zooms around their middle. The zoom
			// counts from the start, not step by step: small steps would round away.
			panBy(mid.x - pinch.mid.x, mid.y - pinch.mid.y)
			setZoom(Math.round(pinch.zoom * (dist / pinch.dist) * 100) / 100, mid)
			pinch.mid = mid
			return
		}
		if (!start || event.pointerId !== start.id) return
		const dx = event.clientX - start.x
		const dy = event.clientY - start.y
		if (!dragging.value) {
			if (Math.hypot(dx, dy) < DRAG_THRESHOLD) return
			dragging.value = true
			springing.value = false
			followPaused.value = true
			capture(start.target, event.pointerId)
		}
		// Each move from the start: the resistance stays steady however fast the hand is.
		over.x = 0
		over.y = 0
		panBy(dx, dy, { x: start.panX, y: start.panY })
	}

	function onPointerUp(event) {
		const id = event?.pointerId
		if (id !== undefined && !pointers.delete(id)) return
		if (id === undefined) pointers.clear()
		if (pinch) {
			// A third finger lifting changes nothing.
			if (!pinch.ids.includes(id) && id !== undefined) return
			const target = pinch.target
			const rest = pinch.ids.find((other) => other !== id && pointers.has(other))
			pinch = null
			suppressClick = true
			// One pinch finger left: it goes on as a drag from where it is, without a jump.
			if (rest !== undefined) {
				startDrag(rest, target)
				return
			}
		} else if (id !== undefined && start?.id !== id) {
			// Not the finger that pans (a finger noted on a chip): nothing to end.
			return
		}
		if (dragging.value) suppressClick = true
		start = null
		dragging.value = false
		springBack()
	}

	/** Swallows the click that ends a drag, so dragging over a chip does not open its menu. */
	function onClickCapture(event) {
		if (!suppressClick) return
		suppressClick = false
		event.stopPropagation()
		event.preventDefault()
	}

	// --- Scroll: pan; with Ctrl/⌘ (and a trackpad pinch, which arrives as ctrl+wheel) zoom.
	let wheelTimer = null
	function onWheel(event) {
		if (event.ctrlKey || event.metaKey) {
			const box = event.currentTarget.getBoundingClientRect()
			// A mouse notch (~100) is about ×1.3; a trackpad pinch sends many small steps.
			const delta = event.deltaMode === 1 ? event.deltaY * 16 : event.deltaY
			zoomBy(Math.exp(-delta * 0.0025), { x: event.clientX - box.left, y: event.clientY - box.top })
			return
		}
		const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? view.height : 1
		let dx = -event.deltaX * unit
		let dy = -event.deltaY * unit
		if (event.shiftKey && !event.deltaX) [dx, dy] = [dy, 0]
		springing.value = false
		followPaused.value = true
		panBy(dx, dy)
		clearTimeout(wheelTimer)
		wheelTimer = setTimeout(springBack, WHEEL_SETTLE_MS)
	}

	/** My chip moved: keep it inside the view, unless I am looking around by hand. */
	function followChip(x, y, { resume = true } = {}) {
		if (resume) followPaused.value = false
		if (followPaused.value || dragging.value || !tile.value) return
		const at = toView(x + 0.5, y + 0.5)
		pan.x = follow(pan.x, at.x, view.width, view.width * FOLLOW_SHARE)
		pan.y = follow(pan.y, at.y, view.height, view.height * FOLLOW_SHARE)
		clampPan()
	}

	/** The first time the view has a size: centre on my chip (or the grid). */
	function place(x, y) {
		if (!tile.value) return
		const { cols, rows } = grid()
		centerOn(x ?? cols / 2, y ?? rows / 2)
		placed = true
	}

	function fit(x, y) {
		setZoom(1)
		place(x, y)
	}

	// The view, the grid or the image changed size: keep the same middle, inside the edges.
	watch([() => view.width, () => view.height, tile, () => canvas.value.x, () => canvas.value.y, () => canvas.value.w, () => canvas.value.h], () => {
		if (placed) clampPan()
	})

	return {
		zoom,
		tile,
		baseTile,
		pan,
		canvas,
		size,
		origin,
		transform,
		springing,
		dragging,
		followPaused,
		setZoom,
		zoomBy,
		centerOn,
		toView,
		place,
		fit,
		followChip,
		panBy,
		springBack,
		onPointerDown,
		onPointerMove,
		onPointerUp,
		onClickCapture,
		onWheel,
		isPlaced: () => placed,
		// A finger (or the mouse) is down on the map: a second finger may join for a pinch.
		isPressed: () => pointers.size > 0,
	}
}
