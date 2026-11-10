/**
 * One step of the walk through the ideas up for vote (#1842): the idea after `name` in `names`,
 * and where `name` stands (1-based, 0 when it is not in the walk).
 */
export function walkStep(names, name) {
	const index = (names || []).indexOf(name)
	const total = (names || []).length
	if (index < 0) return { next: null, position: 0, total }
	return { next: names[index + 1] || null, position: index + 1, total }
}
