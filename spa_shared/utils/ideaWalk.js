/**
 * One step of the walk through the ideas up for vote (#1845): the idea after `name` in `names`,
 * and where `name` stands (1-based, 0 when it is not in the walk).
 */
export function walkStep(names, name) {
	const list = names || []
	const index = list.indexOf(name)
	if (index < 0) return { next: null, position: 0, total: list.length }
	return { next: list[index + 1] || null, position: index + 1, total: list.length }
}

/**
 * The order a walk follows, taken once so a vote that reorders the list does not make the walk
 * skip or repeat ideas. `loadNames` returns the list's current order; it is called when an idea
 * is not in the walk yet (first idea, or a direct link).
 */
export function createWalkQueue(loadNames) {
	let names = []
	// Counts resets: an order that arrives after a reset belongs to an ended walk and is not kept.
	let generation = 0
	return {
		reset() {
			names = []
			generation += 1
		},
		async step(name) {
			if (names.includes(name)) return walkStep(names, name)
			const started = generation
			const loaded = (await loadNames()) || []
			if (started !== generation) return walkStep(loaded, name)
			names = loaded
			return walkStep(names, name)
		},
	}
}
