<template>
	<!--
		My timesheet timer on my own chip (#2101): the same control as in the Personal Cockpit's top
		bar (#1572), with the same dialogs, so both always show the same timer.
		Nothing while the state loads or when my user has no Employee.
	-->
	<section v-if="timer.state?.available" class="space-y-2" data-testid="my-timesheet">
		<div class="text-xs font-medium text-ink-gray-5">{{ __("Timesheet") }}</div>
		<TimerControl />
	</section>
</template>

<script setup>
import { onMounted } from "vue"
import TimerControl from "@spa/components/timesheet/TimerControl.vue"
import { useUserRealtime } from "@spa/composables/useUserRealtime.js"
import { __ } from "@spa/utils/i18n.js"
import { loadTimer, timer } from "@spa/timerStore.js"

// Started or stopped in the Personal Cockpit or in Desk: follow it here.
useUserRealtime("cockpit_timer_changed", loadTimer, { debounceMs: 300 })
onMounted(loadTimer)
</script>
