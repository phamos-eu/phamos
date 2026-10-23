<template>
	<!-- Customer → Implementation (#1672). A level with one option is set and shown read-only. -->
	<div class="flex-shrink-0 border-b border-outline-gray-2" :class="collapsed ? 'px-2 py-2' : 'px-3 py-2.5'">
		<div class="flex items-center gap-2" :class="collapsed ? 'flex-col' : ''">
			<CustomerLogo :customer="customer" />
			<div v-if="!collapsed" class="min-w-0 flex-1">
				<div class="text-2xs text-ink-gray-5">{{ __("Implementation Cockpit") }}</div>
				<div class="truncate text-sm font-semibold text-ink-gray-9">
					{{ customer?.customer_name || __("No implementation") }}
				</div>
			</div>
			<button
				type="button"
				class="rounded p-1.5 text-ink-gray-5 hover:bg-surface-gray-2 hover:text-ink-gray-8"
				:title="collapsed ? __('Expand') : __('Collapse')"
				@click="emit('toggle')"
			>
				<FeatherIcon :name="collapsed ? 'chevrons-right' : 'chevrons-left'" class="h-4 w-4" />
			</button>
		</div>

		<div v-if="!collapsed && customers.length" class="mt-2.5 flex flex-col gap-2">
			<label class="flex flex-col gap-1">
				<span class="text-2xs font-semibold uppercase tracking-wide text-ink-gray-5">{{ __("Customer") }}</span>
				<select
					v-if="customers.length > 1"
					class="h-8 w-full rounded border border-outline-gray-2 bg-surface-white px-2 text-sm text-ink-gray-9 focus:border-outline-gray-4 focus:ring-0"
					:value="customer?.name"
					@change="pickCustomer($event.target.value)"
				>
					<option v-for="c in customers" :key="c.name" :value="c.name">{{ c.customer_name }}</option>
				</select>
				<div v-else class="flex h-8 items-center truncate rounded bg-surface-gray-2 px-2 text-sm text-ink-gray-7" aria-readonly="true">
					{{ customer?.customer_name }}
				</div>
			</label>

			<label class="flex flex-col gap-1">
				<span class="text-2xs font-semibold uppercase tracking-wide text-ink-gray-5">{{ __("Implementation") }}</span>
				<select
					v-if="implementations.length > 1"
					class="h-8 w-full rounded border border-outline-gray-2 bg-surface-white px-2 text-sm text-ink-gray-9 focus:border-outline-gray-4 focus:ring-0"
					:value="route.params.implementation"
					@change="pickImplementation($event.target.value)"
				>
					<option v-for="i in implementations" :key="i.name" :value="i.name">{{ i.name }}</option>
				</select>
				<div v-else class="truncate rounded bg-surface-gray-2 px-2 py-1.5 text-sm text-ink-gray-7" aria-readonly="true">
					{{ route.params.implementation }}
				</div>
				<span v-if="currentPhase" class="text-2xs text-ink-gray-5">{{ currentPhase }}</span>
			</label>
		</div>
	</div>
</template>

<script setup>
import { computed } from "vue"
import { useRoute, useRouter } from "vue-router"
import { __ } from "@spa/utils/i18n.js"
import { customerOf, scope } from "../scopeStore.js"
import CustomerLogo from "./CustomerLogo.vue"

defineProps({ collapsed: { type: Boolean, default: false } })
const emit = defineEmits(["toggle"])

const route = useRoute()
const router = useRouter()

const customers = computed(() => scope.customers)
const customer = computed(() => customerOf(route.params.implementation) || null)
const implementations = computed(() => customer.value?.implementations || [])
const currentPhase = computed(() => {
	const impl = implementations.value.find((i) => i.name === route.params.implementation)
	return [impl?.phase, impl?.status].filter(Boolean).join(" · ")
})

function pickCustomer(name) {
	const target = customers.value.find((c) => c.name === name)
	const first = target?.implementations[0]?.name
	if (first) pickImplementation(first)
}

function pickImplementation(name) {
	// Stay on the same section when switching.
	const section = route.name && route.name !== "Home" ? route.name : "Overview"
	router.push({ name: section, params: { implementation: name } })
}
</script>
