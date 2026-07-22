<script setup lang="ts">
import { reactive, shallowRef } from 'vue'
import { ElMessage } from 'element-plus'
import { createDefaultModelSummaryFilters, type ModelSummaryFilters } from '../../composables/useModelSummary'

const form = reactive<ModelSummaryFilters>(createDefaultModelSummaryFilters())
const submitting = shallowRef(false)
const emit = defineEmits<{ apply: [filters: ModelSummaryFilters]; reset: [] }>()

function apply() {
  if (!form.bestOnly && !form.stockKeyword.trim()) {
    ElMessage.warning('查询全部结果时，请输入股票代码、股票名或任务名')
    return
  }
  submitting.value = true
  emit('apply', { ...form })
  submitting.value = false
}

function reset() {
  Object.assign(form, createDefaultModelSummaryFilters())
  emit('reset')
}
</script>

<template>
  <el-form class="model-summary-filter" label-position="top" @submit.prevent="apply">
    <el-form-item label="任务类型"><el-select v-model="form.taskType" clearable placeholder="全部类型"><el-option label="C3" value="google_sheet" /><el-option label="C4" value="google_sheet_C4" /><el-option label="C5" value="google_sheet_C5" /><el-option label="C7" value="google_sheet_C7" /><el-option label="回测" value="backtest_training" /></el-select></el-form-item>
    <el-form-item label="股票 / 任务"><el-input v-model="form.stockKeyword" clearable placeholder="代码、股票名或任务名" /></el-form-item>
    <el-form-item label="市场"><el-select v-model="form.marketType" clearable placeholder="全部市场"><el-option label="A股" value="cn" /><el-option label="美股" value="us" /></el-select></el-form-item>
    <el-form-item label="年份 / 区间"><el-select v-model="form.periodFilter" clearable placeholder="全部区间"><el-option label="近 1 年" value="recent_1y" /><el-option label="近 3 年" value="recent_3y" /><el-option v-for="year in [2026, 2025, 2024, 2023, 2022, 2021, 2020, 2019]" :key="year" :label="`整年 ${year}`" :value="`full_${year}`" /></el-select></el-form-item>
    <el-form-item label="结果日期"><el-date-picker v-model="form.resultDateFrom" value-format="YYYY-MM-DD" type="date" placeholder="开始日期" /><span class="model-summary-filter__range">至</span><el-date-picker v-model="form.resultDateTo" value-format="YYYY-MM-DD" type="date" placeholder="结束日期" /></el-form-item>
    <el-form-item label="汇总方式"><el-segmented v-model="form.summaryType" :options="[{ label: '任务汇总', value: 'task' }, { label: '股票汇总', value: 'stock' }]" /></el-form-item>
    <el-form-item label="数据范围"><el-select v-model="form.bestOnly"><el-option label="仅最优" :value="true" /><el-option label="全部结果" :value="false" /></el-select></el-form-item>
    <el-form-item label="超额收益"><el-select v-model="form.excessReturnMin" clearable placeholder="全部"><el-option label="大于 0%" value="0" /><el-option label="大于 10%" value="10" /><el-option label="大于 20%" value="20" /><el-option label="大于 50%" value="50" /><el-option label="大于 100%" value="100" /></el-select></el-form-item>
    <el-form-item label="任务 ID"><el-input v-model="form.taskId" clearable placeholder="精确任务 ID" /></el-form-item>
    <el-form-item label="结果 ID"><el-input v-model="form.resultId" clearable inputmode="numeric" placeholder="结果 ID" /></el-form-item>
    <div class="model-summary-filter__actions"><el-button type="primary" :loading="submitting" native-type="submit">查询</el-button><el-button @click="reset">重置</el-button></div>
  </el-form>
</template>

<style scoped>
.model-summary-filter { display: grid; grid-template-columns: repeat(5, minmax(160px, 1fr)); gap: 0 12px; }.model-summary-filter :deep(.el-form-item) { margin-bottom: 14px; }.model-summary-filter :deep(.el-form-item__label) { color: var(--admin-text-regular); font-size: 13px; line-height: 20px; }.model-summary-filter :deep(.el-select),.model-summary-filter :deep(.el-input) { width: 100%; }.model-summary-filter__range { margin: 0 6px; color: var(--admin-text-muted); font-size: 13px; }.model-summary-filter :deep(.el-date-editor) { width: calc(50% - 15px); }.model-summary-filter__actions { display: flex; align-items: end; gap: 8px; padding-bottom: 14px; }@media (max-width: 1280px) { .model-summary-filter { grid-template-columns: repeat(3, minmax(160px, 1fr)); } }@media (max-width: 760px) { .model-summary-filter { grid-template-columns: 1fr; }.model-summary-filter__actions { padding-bottom: 0; } }
</style>
