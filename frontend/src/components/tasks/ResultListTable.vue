<script setup lang="ts">
import { Delete, View } from '@element-plus/icons-vue'
import type { TaskResultItem } from '../../types/api'
import { formatDateTime } from '../../utils/format'
import { shortIdentifier, taskTypeText, xplStatusText, xplStatusType } from '../../utils/task'

defineProps<{
  items: TaskResultItem[]
  loading: boolean
  canDelete: boolean
}>()

const emit = defineEmits<{
  view: [result: TaskResultItem]
  remove: [result: TaskResultItem]
}>()
</script>

<template>
  <el-table v-loading="loading" :data="items" class="result-list-table" empty-text="暂无结果">
    <el-table-column label="任务" min-width="230">
      <template #default="{ row }">
        <div class="result-list-table__task">
          <strong>{{ row.task_name || '未命名任务' }}</strong>
          <span><el-tag type="info" effect="plain">{{ taskTypeText(row.task_type) }}</el-tag><el-tooltip :content="row.task_id"><i>{{ shortIdentifier(row.task_id) }}</i></el-tooltip></span>
        </div>
      </template>
    </el-table-column>
    <el-table-column label="标的与区间" min-width="190">
      <template #default="{ row }">
        <div class="result-list-table__summary">
          <strong>{{ row.summary?.stock_code || '-' }}</strong>
          <span>{{ row.summary?.stock_name || row.summary?.period || '未记录区间' }}</span>
          <span v-if="row.summary?.stock_name && row.summary?.period">{{ row.summary.period }}</span>
          <el-tooltip v-if="row.summary?.kline_date_range" :content="`K 线范围：${row.summary.kline_date_range}`"><span class="result-list-table__kline">K 线范围</span></el-tooltip>
        </div>
      </template>
    </el-table-column>
    <el-table-column label="参数组合" min-width="240">
      <template #default="{ row }">
        <div v-if="row.summary?.parameter_items?.length" class="result-list-table__parameters">
          <span v-for="item in row.summary.parameter_items" :key="`${row.id}-${item.label}`" class="result-list-table__parameter"><b>{{ item.label }}</b>{{ item.value }}</span>
        </div>
        <span v-else>-</span>
      </template>
    </el-table-column>
    <el-table-column label="执行信息" width="144">
      <template #default="{ row }">
        <div class="result-list-table__model">
          <el-tag :type="row.success ? 'success' : 'danger'" effect="light">{{ row.success ? '成功' : '失败' }}</el-tag>
          <span>{{ row.summary?.model_count || 0 }} 个模型 · 步骤 {{ row.step_index ?? '-' }}</span>
          <el-tag v-if="row.summary?.analysis_status" :type="xplStatusType(row.summary.analysis_status)" effect="plain">{{ xplStatusText(row.summary.analysis_status) }}</el-tag>
        </div>
      </template>
    </el-table-column>
    <el-table-column label="记录时间" width="176"><template #default="{ row }">{{ formatDateTime(row.timestamp) }}</template></el-table-column>
    <el-table-column fixed="right" label="操作" width="128"><template #default="{ row }"><div class="result-list-table__actions"><el-button link type="primary" :icon="View" @click="emit('view', row)">详情</el-button><el-button v-if="canDelete" link type="danger" :icon="Delete" @click="emit('remove', row)">删除</el-button></div></template></el-table-column>
  </el-table>
</template>

<style scoped>
.result-list-table { width: 100%; }
.result-list-table__task,
.result-list-table__summary,
.result-list-table__model { display: grid; gap: 4px; min-width: 0; }
.result-list-table__task > strong,
.result-list-table__summary > strong,
.result-list-table__model > strong { color: var(--admin-text); font-weight: 600; }
.result-list-table__task > span { display: flex; align-items: center; gap: 6px; min-width: 0; }
.result-list-table__task i,
.result-list-table__summary > span,
.result-list-table__model > span { overflow: hidden; color: var(--admin-text-muted); font-size: 12px; font-style: normal; text-overflow: ellipsis; white-space: nowrap; }
.result-list-table__kline { color: var(--admin-primary) !important; cursor: help; }
.result-list-table__parameters { display: flex; flex-wrap: wrap; gap: 6px; }
.result-list-table__parameter { display: inline-flex; align-items: center; gap: 4px; max-width: 112px; min-height: 24px; padding: 0 7px; overflow: hidden; border: 1px solid var(--admin-primary-border); border-radius: 4px; color: var(--admin-text-regular); font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.result-list-table__parameter b { color: var(--admin-text-muted); font-weight: 500; }
.result-list-table__model :deep(.el-tag) { justify-self: start; }
.result-list-table__actions { display: flex; align-items: center; gap: 8px; min-width: max-content; white-space: nowrap; }
.result-list-table__actions :deep(.el-button + .el-button) { margin-left: 0; }
</style>
