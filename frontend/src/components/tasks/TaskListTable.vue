<script setup lang="ts">
import { Delete, EditPen, MoreFilled, RefreshRight, View } from '@element-plus/icons-vue'
import type { TaskItem } from '../../types/api'
import { formatDateTime, taskStatusText, taskStatusType } from '../../utils/format'
import { taskProgress, taskTypeText } from '../../utils/task'

defineProps<{
  items: TaskItem[]
  loading: boolean
  canCancel: boolean
  canRestart: boolean
  canDelete: boolean
  canEdit: boolean
}>()

const emit = defineEmits<{
  selectionChange: [tasks: TaskItem[]]
  view: [task: TaskItem]
  cancel: [task: TaskItem]
  restart: [task: TaskItem]
  restartFresh: [task: TaskItem]
  createRestart: [task: TaskItem]
  edit: [task: TaskItem]
  viewExecution: [task: TaskItem]
  remove: [task: TaskItem]
}>()

function canSelect(task: TaskItem) {
  return task.status !== 'running'
}
</script>

<template>
  <el-table v-loading="loading" :data="items" row-key="id" class="task-list-table" empty-text="暂无任务" @selection-change="emit('selectionChange', $event)">
    <el-table-column type="selection" width="48" :selectable="canSelect" />
    <el-table-column label="任务" min-width="240">
      <template #default="{ row }">
        <div class="task-list-table__name">
          <el-tooltip :content="row.name" placement="top">
            <strong>{{ row.name }}</strong>
          </el-tooltip>
          <span v-if="row.description">{{ row.description }}</span>
        </div>
      </template>
    </el-table-column>
    <el-table-column label="类型" min-width="142">
      <template #default="{ row }">
        <el-tag type="info" effect="plain">{{ taskTypeText(row.task_type) }}</el-tag>
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
        <span class="task-list-table__progress">{{ row.current_step || 0 }} / {{ row.total_steps || 0 }}</span>
      </template>
    </el-table-column>
    <el-table-column label="开始时间" width="174">
      <template #default="{ row }">{{ formatDateTime(row.start_time) }}</template>
    </el-table-column>
    <el-table-column label="创建时间" width="174">
      <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
    </el-table-column>
    <el-table-column fixed="right" label="操作" width="208">
      <template #default="{ row }">
        <div class="task-list-table__actions">
          <el-button link type="primary" :icon="View" @click="emit('view', row)">详情</el-button>
          <el-button v-if="canCancel && row.status === 'running'" link type="warning" @click="emit('cancel', row)">停止</el-button>
          <el-button v-else-if="canRestart && row.status !== 'running'" link type="primary" :icon="RefreshRight" @click="emit('restart', row)">重启</el-button>
          <el-button v-if="canDelete && row.status !== 'running'" link type="danger" :icon="Delete" @click="emit('remove', row)">删除</el-button>
          <el-dropdown v-if="row.status !== 'running' || canRestart" trigger="click" @command="(command) => emit(command, row)">
            <el-button link :icon="MoreFilled" aria-label="更多任务操作" />
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item v-if="canEdit && row.status !== 'running'" command="edit"><el-icon><EditPen /></el-icon>编辑任务</el-dropdown-item>
                <el-dropdown-item command="viewExecution"><el-icon><View /></el-icon>查看执行详情</el-dropdown-item>
                <el-dropdown-item v-if="canRestart && row.status !== 'running'" command="restartFresh"><el-icon><RefreshRight /></el-icon>从头重启</el-dropdown-item>
                <el-dropdown-item v-if="canRestart && row.status !== 'running'" command="createRestart"><el-icon><RefreshRight /></el-icon>创建重启任务</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </template>
    </el-table-column>
  </el-table>
</template>

<style scoped>
.task-list-table { width: 100%; }

.task-list-table__name {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.task-list-table__name strong,
.task-list-table__name span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-list-table__name strong { color: var(--admin-text); font-weight: 600; }
.task-list-table__name span,
.task-list-table__progress { color: var(--admin-text-muted); font-size: 12px; }
.task-list-table__progress { display: block; margin-top: 4px; }
.task-list-table__actions { display: flex; align-items: center; gap: 8px; min-width: max-content; white-space: nowrap; }
.task-list-table__actions :deep(.el-button + .el-button) { margin-left: 0; }
</style>
