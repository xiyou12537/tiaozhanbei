<template>
  <teleport to="body">
    <transition name="modal-fade">
      <div v-if="visible" class="auth-overlay" @click.self="$emit('close')">
        <div class="auth-dialog">
          <AuthFormCard
            :initialTab="initialTab"
            :showClose="true"
            @close="$emit('close')"
            @success="payload => $emit('success', payload)"
            @tab-change="tab => $emit('tab-change', tab)"
          />
        </div>
      </div>
    </transition>
  </teleport>
</template>

<script setup>
import AuthFormCard from './AuthFormCard.vue'

defineProps({
  visible: { type: Boolean, default: false },
  initialTab: { type: String, default: 'login' },
})

defineEmits(['close', 'success', 'tab-change'])
</script>

<style scoped>
.auth-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: rgba(3, 10, 18, 0.72);
  backdrop-filter: blur(8px);
}

.auth-dialog {
  width: min(100%, 460px);
}

.modal-fade-enter-active,
.modal-fade-leave-active {
  transition: opacity 0.2s ease;
}

.modal-fade-enter-from,
.modal-fade-leave-to {
  opacity: 0;
}
</style>
