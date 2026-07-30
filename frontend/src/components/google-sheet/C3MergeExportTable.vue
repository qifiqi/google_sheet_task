<script setup lang="ts">
import { formatDateTime, taskStatusText, taskStatusType } from '../../utils/format'
import { taskProgress } from '../../utils/task'
import type { TaskItem } from '../../types/api'

const props = defineProps<{
  items: TaskItem[]
  loading: boolean
  selectedIds: Set<string>
  selectedCount: number
  maxSelection: number
}>()

const emit = defineEmits<{
  toggle: [task: TaskItem, checked: boolean]
}>()

function isSelectionDisabled(task: TaskItem) {
  return !props.selectedIds.has(task.id) && props.selectedCount >= props.maxSelection
}
</script>

<template>
  <el-table v-loading="loading" :data="items" row-key="id" class="c3-merge-export-table" empty-text="暂无匹配任务">
    <el-table-column width="52" align="center">
      <template #header><span class="c3-merge-export-table__select-label">选择</span></template>
      <template #default="{ row }">
        <el-checkbox
          :model-value="selectedIds.has(row.id)"
          :disabled="isSelectionDisabled(row)"
          :aria-label="`${selectedIds.has(row.id) ? '取消选择' : '选择'}任务 ${row.name}`"
          @change="emit('toggle', row, Boolean($event))"
        />
      </template>
    </el-table-column>
    <el-table-column label="任务" min-width="280">
      <template #default="{ row }">
        <div class="c3-merge-export-table__task">
          <el-tooltip :content="row.name" placement="top">
            <strong>{{ row.name }}</strong>
          </el-tooltip>
          <span>{{ row.id }}</span>
        </div>
      </template>
    </el-table-column>
    <el-table-column label="状态" width="106">
      <template #default="{ row }">
        <el-tag :type="taskStatusType(row.status)" effect="light">{{ taskStatusText(row.status) }}</el-tag>
      </template>
    </el-table-column>
    <el-table-column label="进度" width="150">
      <template #default="{ row }">
        <el-progress :percentage="taskProgress(row)" :stroke-width="6" :show-text="false" />
        <span class="c3-merge-export-table__progress">{{ row.current_step || 0 }} / {{ row.total_steps || 0 }}</span>
      </template>
    </el-table-column>
    <el-table-column label="创建时间" width="174">
      <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
    </el-table-column>
    <el-table-column label="开始时间" width="174">
      <template #default="{ row }">{{ formatDateTime(row.start_time) }}</template>
    </el-table-column>
    <el-table-column label="结束时间" width="174">
      <template #default="{ row }">{{ formatDateTime(row.end_time) }}</template>
    </el-table-column>
  </el-table>
</template>

<style scoped>
.c3-merge-export-table { width: 100%; }
.c3-merge-export-table__select-label { color: var(--admin-text-regular); font-size: 12px; font-weight: 600; }
.c3-merge-export-table__task { display: grid; gap: 2px; min-width: 0; }
.c3-merge-export-table__task strong,
.c3-merge-export-table__task span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.c3-merge-export-table__task strong { color: var(--admin-text); font-weight: 600; }
.c3-merge-export-table__task span,
.c3-merge-export-table__progress { color: var(--admin-text-muted); font-size: 12px; }
.c3-merge-export-table__progress { display: block; margin-top: 4px; }
</style>
