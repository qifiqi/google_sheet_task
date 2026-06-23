<template>
  <div v-if="totalSteps > 0" class="n-progress-cell">
    <n-progress
      type="line"
      :percentage="percentage"
      :height="6"
      :border-radius="3"
      :show-indicator="false"
      :color="progressColor"
      rail-color="rgba(30, 41, 59, 0.6)"
    />
    <span class="n-progress-cell__text">{{ currentStep }} / {{ totalSteps }}</span>
  </div>
  <span v-else class="n-progress-cell__empty">-</span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  currentStep: { type: Number, default: 0 },
  totalSteps: { type: Number, default: 0 },
})

const percentage = computed(() =>
  props.totalSteps > 0 ? Math.round((props.currentStep / props.totalSteps) * 100) : 0
)

const progressColor = computed(() => {
  if (percentage.value >= 100) return '#10b981'
  if (percentage.value >= 50) return '#6366f1'
  return '#f59e0b'
})
</script>

<style scoped>
.n-progress-cell {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 140px;
}

.n-progress-cell :deep(.n-progress) {
  flex: 1;
}

.n-progress-cell__text {
  font-size: 12px;
  color: #94a3b8;
  white-space: nowrap;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
}

.n-progress-cell__empty {
  color: #475569;
}
</style>
