<template>
  <div class="task-progress-cell">
    <el-progress
      v-if="totalSteps > 0"
      :percentage="percentage"
      :format="() => `${currentStep}/${totalSteps}`"
    />
    <span v-else class="task-progress-cell__empty">-</span>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  currentStep: { type: Number, default: 0 },
  totalSteps: { type: Number, default: 0 },
})

const percentage = computed(() => {
  if (props.totalSteps <= 0) return 0
  return Math.min(100, Math.round((props.currentStep / props.totalSteps) * 100))
})
</script>

<style lang="scss" scoped>
.task-progress-cell {
  min-width: 100px;
  display: flex;
  align-items: center;

  :deep(.el-progress) {
    width: 100%;
    align-items: center;
  }

  :deep(.el-progress-bar) {
    padding-right: 0;
    margin-right: 0;
  }

  :deep(.el-progress__text) {
    font-size: var(--app-font-xs) !important;
    color: var(--app-text-muted);
    min-width: 42px;
    text-align: right;
  }

  &__empty {
    color: var(--app-text-subtle);
    font-size: var(--app-font-sm);
  }
}
</style>
