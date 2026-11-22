// Every person's own ring colour in Ophice (#2053), the same on every screen. Blues are left
// out: blue is my own ring.
export function ringHue(user = "") {
	let hash = 0
	for (const char of user) hash = (hash * 31 + char.charCodeAt(0)) >>> 0
	const hue = hash % 300
	return hue >= 190 ? hue + 60 : hue
}
