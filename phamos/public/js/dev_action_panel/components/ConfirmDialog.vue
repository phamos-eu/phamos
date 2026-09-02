<script setup>
const props = defineProps({
  title: { type: String, default: "Confirm" },
  message: { type: String, default: "" },
  confirmLabel: { type: String, default: "Yes" },
  cancelLabel: { type: String, default: "No" },
});
const emit = defineEmits(["confirm", "cancel"]);

function onKey(e) {
  if (e.key === "Escape") emit("cancel");
  if (e.key === "Enter") emit("confirm");
}
</script>

<template>
  <div class="cd-backdrop" @click.self="emit('cancel')" @keydown="onKey">
    <div class="cd" role="dialog" aria-modal="true">
      <div class="cd__body">
        <h3 class="cd__title">{{ title }}</h3>
        <p class="cd__message">{{ message }}</p>
      </div>
      <div class="cd__actions">
        <button class="cd__btn cd__btn--ghost" @click="emit('cancel')">{{ cancelLabel }}</button>
        <button class="cd__btn cd__btn--primary" @click="emit('confirm')">{{ confirmLabel }}</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.cd-backdrop {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.4);
  backdrop-filter: blur(3px);
  display: flex; align-items: center; justify-content: center;
  z-index: 1100; padding: 20px;
}
.cd {
  background: var(--card-bg);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  width: 360px; max-width: 100%;
  padding: 22px 24px 20px;
  box-shadow: var(--shadow-md, 0 8px 32px rgba(0,0,0,0.18));
  animation: cd-in 0.18s cubic-bezier(0.34,1.56,0.64,1);
}
@keyframes cd-in { from { transform: scale(0.92); opacity: 0; } }

.cd__body { margin-bottom: 18px; }
.cd__title { margin: 0 0 8px; font-size: 15px; font-weight: 700; color: var(--text-color); }
.cd__message { margin: 0; font-size: 13px; line-height: 1.5; color: var(--text-muted); }

.cd__actions { display: flex; gap: 10px; justify-content: flex-end; }
.cd__btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 7px 14px; border-radius: 7px;
  font-size: 13px; font-weight: 600; cursor: pointer;
  border: 1px solid transparent; line-height: 1;
  transition: background 0.12s, border-color 0.12s;
}
.cd__btn--ghost { background: none; border-color: var(--border-color); color: var(--text-muted); }
.cd__btn--ghost:hover { background: var(--control-bg); color: var(--text-color); }
.cd__btn--primary { background: var(--primary); color: #fff; border-color: var(--primary); }
.cd__btn--primary:hover { background: var(--blue-700, #1d4ed8); }
</style>
