<script setup lang="ts">
import { Calendar } from '@element-plus/icons-vue'
import type { DashboardPeriodDays } from '../../composables/useDashboardOverview'

const model = defineModel<DashboardPeriodDays>({ required: true })

const options: Array<{ label: string; value: DashboardPeriodDays }> = [
  { label: '近 7 天', value: 7 },
  { label: '近 30 天', value: 30 },
  { label: '近 90 天', value: 90 },
]
</script>

<template>
  <label class="period-control">
    <span>统计周期</span>
    <el-select v-model="model" size="small" aria-label="仪表盘统计周期">
      <template #prefix><el-icon><Calendar /></el-icon></template>
      <el-option v-for="option in options" :key="option.value" :label="option.label" :value="option.value" />
    </el-select>
  </label>
</template>

<style scoped>
.period-control {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--admin-text-muted);
  font-size: 12px;
  white-space: nowrap;
}

.period-control :deep(.el-select) {
  width: 126px;
}
</style>
