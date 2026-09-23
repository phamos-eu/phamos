<template>
	<div class="flex h-full flex-col bg-gray-50 text-gray-900">
		<header
			class="flex items-center justify-between border-b border-gray-200 bg-white px-5 py-3"
		>
			<div>
				<div class="text-lg font-semibold tracking-tight">I Own My Work</div>
				<div class="text-sm text-gray-600">
					Internal issues — created by you and assigned to you
				</div>
			</div>
			<div class="flex items-center gap-2">
				<a
					href="/app"
					class="rounded-md px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100"
				>
					Desk
				</a>
				<button
					class="rounded-md px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100"
					@click="session.logout.submit()"
				>
					Log out
				</button>
			</div>
		</header>
		<main class="min-h-0 flex-1 overflow-hidden">
			<router-view />
		</main>
	</div>
</template>

<script setup>
import { inject } from "vue"

const session = inject("$session")
</script>
