// A test environment like "node" (no DOM), but with the client build of .vue files, so a component's
// <script setup> can run on its own. Vitest's "node" environment would give the SSR build.
export default {
	name: "node-client",
	transformMode: "web",
	setup() {
		return { teardown() {} }
	},
}
