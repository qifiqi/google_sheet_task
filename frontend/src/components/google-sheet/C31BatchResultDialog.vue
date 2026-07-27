<script setup lang="ts">
import { computed } from 'vue'
import { List, View } from '@element-plus/icons-vue'
import type { C31BatchCreateResponse } from '../../types/api'

const open = defineModel<boolean>({ default: false })
const props = defineProps<{ result: C31BatchCreateResponse | null }>()
const emit = defineEmits<{ viewTask: [taskId: string]; viewList: [] }>()

const failuresByTaskId = computed(() => new Map((props.result?.failed_to_start || []).map((item) => [item.task_id, item.error])))
const children = computed(() => props.result?.children || [])
const failedCount = computed(() => Math.max(0, Number(props.result?.total_created || 0) - Number(props.result?.total_started || 0)))

function parameterText(parameters: unknown[][]) {
  return parameters.map((group) => JSON.stringify(group)).join(' | ')
}
</script>

<template>
  <el-dialog v-model="open" title="C31 批量创建结果" width="min(1120px, calc(100vw - 32px))" destroy-on-close>
    <template v-if="result">
      <section class="c31-batch-result__summary">
        <div><span>已创建</span><strong>{{ result.total_created }}</strong></div>
        <div><span>已启动</span><strong class="is-success">{{ result.total_started }}</strong></div>
        <div><span>未启动</span><strong :class="{ 'is-danger': failedCount }">{{ failedCount }}</strong></div>
      </section>
      <el-alert v-if="result.message" :title="result.message" :type="failedCount ? 'warning' : 'success'" :closable="false" show-icon />
      <el-table :data="children" class="c31-batch-result__table" max-height="440">
        <el-table-column label="子任务" min-width="210"><template #default="{ row }"><div class="c31-batch-result__task"><strong>{{ row.task_name }}</strong><span>{{ row.task_id }}</span></div></template></el-table-column>
        <el-table-column label="标的" width="116"><template #default="{ row }">{{ row.stock_code || '-' }}</template></el-table-column>
        <el-table-column label="工作表" min-width="150"><template #default="{ row }"><div class="c31-batch-result__sheet"><strong>{{ row.sheet_name || '-' }}</strong><span>{{ row.spreadsheet_id || '-' }}</span></div></template></el-table-column>
        <el-table-column label="参数组合" min-width="210"><template #default="{ row }"><span class="c31-batch-result__parameters">{{ parameterText(row.parameters) || '-' }}</span></template></el-table-column>
        <el-table-column label="状态" width="104"><template #default="{ row }"><el-tag :type="row.started ? 'success' : 'danger'" effect="light">{{ row.started ? '已启动' : '未启动' }}</el-tag></template></el-table-column>
        <el-table-column label="未启动原因" min-width="190"><template #default="{ row }"><span class="c31-batch-result__error">{{ failuresByTaskId.get(row.task_id) || '-' }}</span></template></el-table-column>
        <el-table-column fixed="right" label="操作" width="84"><template #default="{ row }"><el-button link type="primary" :icon="View" @click="emit('viewTask', row.task_id)">详情</el-button></template></el-table-column>
      </el-table>
    </template>
    <template #footer><el-button :icon="List" @click="emit('viewList')">查看 C3 列表</el-button><el-button type="primary" @click="open = false">关闭</el-button></template>
  </el-dialog>
</template>

<style scoped>
.c31-batch-result__summary { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); margin-bottom: 16px; border: 1px solid var(--admin-border); border-radius: var(--admin-radius); background: var(--admin-surface); }.c31-batch-result__summary div { display: grid; gap: 4px; padding: 14px 16px; border-right: 1px solid var(--admin-border-light); }.c31-batch-result__summary div:last-child { border-right: 0; }.c31-batch-result__summary span { color: var(--admin-text-muted); font-size: 12px; }.c31-batch-result__summary strong { color: var(--admin-text); font-size: 22px; font-weight: 600; }.c31-batch-result__summary .is-success { color: var(--admin-success); }.c31-batch-result__summary .is-danger { color: var(--admin-danger); }.c31-batch-result__table { width: 100%; margin-top: 16px; }.c31-batch-result__task, .c31-batch-result__sheet { display: grid; gap: 3px; min-width: 0; }.c31-batch-result__task strong, .c31-batch-result__sheet strong { overflow: hidden; color: var(--admin-text); font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }.c31-batch-result__task span, .c31-batch-result__sheet span { overflow: hidden; color: var(--admin-text-muted); font-family: Consolas, "Courier New", monospace; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }.c31-batch-result__parameters, .c31-batch-result__error { display: block; overflow-wrap: anywhere; color: var(--admin-text-regular); font: 12px/1.5 Consolas, "Courier New", monospace; }.c31-batch-result__error { color: var(--admin-danger); }@media (max-width: 640px) { .c31-batch-result__summary { grid-template-columns: 1fr; }.c31-batch-result__summary div { border-right: 0; border-bottom: 1px solid var(--admin-border-light); }.c31-batch-result__summary div:last-child { border-bottom: 0; } }
</style>
