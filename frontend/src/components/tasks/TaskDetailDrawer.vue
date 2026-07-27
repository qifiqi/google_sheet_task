<script setup lang="ts">
import { computed } from 'vue'
import { View } from '@element-plus/icons-vue'
import TaskLogList from './TaskLogList.vue'
import type { TaskItem, TaskLogItem } from '../../types/api'
import { formatDateTime, taskStatusText, taskStatusType } from '../../utils/format'
import { taskProgress, taskTypeText } from '../../utils/task'

const open = defineModel<boolean>({ default: false })
const props = defineProps<{
  task: TaskItem | null
  logs: TaskLogItem[]
  logsLoading: boolean
  canEdit: boolean
  canRestart: boolean
}>()
const emit = defineEmits<{
  edit: [task: TaskItem]
  viewExecution: [task: TaskItem]
  restartFresh: [task: TaskItem]
  createRestart: [task: TaskItem]
}>()

const configText = computed(() => JSON.stringify(props.task?.config || {}, null, 2))
</script>

<template>
  <el-drawer v-model="open" title="任务详情" size="min(520px, 100vw)">
    <template v-if="task">
      <el-tabs class="task-detail" stretch>
        <el-tab-pane label="概览">
          <el-descriptions :column="1" border>
            <el-descriptions-item label="任务名称">{{ task.name }}</el-descriptions-item>
            <el-descriptions-item label="任务类型">{{ taskTypeText(task.task_type) }}</el-descriptions-item>
            <el-descriptions-item label="状态"><el-tag :type="taskStatusType(task.status)">{{ taskStatusText(task.status) }}</el-tag></el-descriptions-item>
            <el-descriptions-item label="进度">{{ task.current_step || 0 }} / {{ task.total_steps || 0 }} ({{ taskProgress(task) }}%)</el-descriptions-item>
            <el-descriptions-item label="创建时间">{{ formatDateTime(task.created_at) }}</el-descriptions-item>
            <el-descriptions-item label="开始时间">{{ formatDateTime(task.start_time) }}</el-descriptions-item>
            <el-descriptions-item label="结束时间">{{ formatDateTime(task.end_time) }}</el-descriptions-item>
            <el-descriptions-item v-if="task.error_message" label="错误摘要">{{ task.error_message }}</el-descriptions-item>
          </el-descriptions>
        </el-tab-pane>
        <el-tab-pane label="配置预览"><section class="task-detail__config"><pre>{{ configText }}</pre></section></el-tab-pane>
        <el-tab-pane label="任务日志"><TaskLogList :logs="logs" :loading="logsLoading" empty-description="暂无任务日志" /></el-tab-pane>
      </el-tabs>
      <div class="task-detail__actions">
        <el-button :icon="View" @click="emit('viewExecution', task)">执行详情</el-button>
        <el-button v-if="canEdit && task.status !== 'running'" @click="emit('edit', task)">编辑</el-button>
        <el-button v-if="canRestart && task.status !== 'running'" @click="emit('restartFresh', task)">从头重启</el-button>
        <el-button v-if="canRestart && task.status !== 'running'" type="primary" @click="emit('createRestart', task)">创建重启任务</el-button>
      </div>
    </template>
  </el-drawer>
</template>

<style scoped>
.task-detail { min-height: 0; }
.task-detail__config { display: grid; gap: 8px; }
.task-detail__config pre {
  max-height: 340px;
  margin: 0;
  padding: 14px;
  overflow: auto;
  border: 1px solid var(--admin-border-light);
  border-radius: 6px;
  background: var(--admin-bg);
  color: var(--admin-text-regular);
  font: 12px/1.6 Consolas, "Courier New", monospace;
  white-space: pre-wrap;
  word-break: break-word;
}
.task-detail__actions { display: flex; flex-wrap: wrap; justify-content: end; gap: 8px; padding-top: 16px; }
</style>
