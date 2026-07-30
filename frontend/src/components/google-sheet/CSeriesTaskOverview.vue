<script setup lang="ts">
import { computed } from 'vue'
import type { TaskItem } from '../../types/api'
import { formatDateTime, formatDuration, taskStatusText, taskStatusType } from '../../utils/format'
import { taskProgress, taskTypeText } from '../../utils/task'

const props = defineProps<{
  task: TaskItem
  totalSuccess: number
  totalFailed: number
}>()

const progress = computed(() => taskProgress(props.task))
const totalResults = computed(() => props.totalSuccess + props.totalFailed)
const successRate = computed(() => totalResults.value ? Math.round((props.totalSuccess / totalResults.value) * 100) : 0)
const duration = computed(() => {
  if (!props.task.created_at) return '-'
  const start = new Date(props.task.created_at)
  const end = new Date(props.task.end_time || Date.now())
  return formatDuration(Math.max(0, (end.getTime() - start.getTime()) / 1000))
})
</script>

<template>
  <section class="task-overview" aria-label="任务概览">
    <div class="task-overview__status">
      <span class="task-overview__label">运行状态</span>
      <div class="task-overview__status-value">
        <el-tag :type="taskStatusType(task.status)" effect="light">{{ taskStatusText(task.status) }}</el-tag>
        <strong>{{ progress }}%</strong>
      </div>
      <el-progress :percentage="progress" :show-text="false" :stroke-width="8" :status="task.status === 'error' ? 'exception' : task.status === 'completed' ? 'success' : undefined" />
      <span class="task-overview__hint">{{ task.current_step || 0 }} / {{ task.total_steps || 0 }} 个执行步骤</span>
    </div>

    <div class="task-overview__result">
      <span class="task-overview__label">结果记录</span>
      <div class="task-overview__result-values">
        <strong class="is-success">{{ totalSuccess }}</strong><span>成功</span>
        <strong class="is-danger">{{ totalFailed }}</strong><span>失败</span>
      </div>
      <el-progress :percentage="successRate" :show-text="false" :stroke-width="8" :status="totalFailed ? 'exception' : 'success'" />
      <span class="task-overview__hint">当前已生成 {{ totalResults }} 条结果</span>
    </div>

    <section class="task-overview__metadata" aria-label="任务详细信息">
      <div class="task-overview__metadata-item">
        <span>任务类型</span>
        <strong>{{ taskTypeText(task.task_type) }}</strong>
      </div>
      <div class="task-overview__metadata-item">
        <span>任务 ID</span>
        <strong class="task-overview__id">{{ task.id }}</strong>
      </div>
      <div class="task-overview__metadata-item">
        <span>创建时间</span>
        <strong>{{ formatDateTime(task.created_at) }}</strong>
      </div>
      <div class="task-overview__metadata-item">
        <span>执行时长</span>
        <strong>{{ duration }}</strong>
      </div>
      <div class="task-overview__metadata-item">
        <span>开始时间</span>
        <strong>{{ formatDateTime(task.start_time) }}</strong>
      </div>
      <div class="task-overview__metadata-item">
        <span>结束时间</span>
        <strong>{{ formatDateTime(task.end_time) }}</strong>
      </div>
      <div v-if="task.error_message" class="task-overview__metadata-item task-overview__metadata-item--error">
        <span>错误摘要</span>
        <strong>{{ task.error_message }}</strong>
      </div>
    </section>
  </section>
</template>

<style scoped>
.task-overview {
  display: grid;
  grid-template-columns: minmax(190px, 0.3fr) minmax(190px, 0.3fr) minmax(0, 1fr);
  gap: 16px;
}

.task-overview__status,
.task-overview__result {
  display: grid;
  align-content: start;
  gap: 12px;
  padding: 18px 20px;
  border: 1px solid var(--admin-border);
  border-radius: var(--admin-radius);
  background: var(--admin-surface);
}

.task-overview__label,
.task-overview__hint,
.task-overview__metadata-item span {
  color: var(--admin-text-muted);
  font-size: 13px;
}

.task-overview__status-value,
.task-overview__result-values {
  display: flex;
  align-items: end;
  gap: 7px;
}

.task-overview__status-value {
  align-items: center;
  justify-content: space-between;
}

.task-overview__status-value strong,
.task-overview__result-values strong {
  color: var(--admin-text);
  font-size: 28px;
  font-weight: 600;
  line-height: 32px;
}

.task-overview__result-values {
  display: grid;
  grid-template-columns: auto auto auto auto;
  justify-content: start;
}

.task-overview__result-values span {
  color: var(--admin-text-muted);
  font-size: 12px;
}

.task-overview__metadata {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  align-content: stretch;
  gap: 8px;
  padding: 8px;
  border: 1px solid var(--admin-border);
  border-radius: var(--admin-radius);
  background: var(--admin-surface);
}

.task-overview__metadata-item {
  display: grid;
  align-content: center;
  min-width: 0;
  min-height: 58px;
  gap: 4px;
  padding: 8px 10px;
  border-radius: 5px;
  background: var(--admin-bg);
}

.task-overview__metadata-item strong {
  overflow: hidden;
  color: var(--admin-text);
  font-size: 13px;
  font-weight: 500;
  line-height: 20px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-overview__metadata-item--error {
  grid-column: 1 / -1;
}

.task-overview__metadata-item--error strong {
  color: var(--admin-danger);
}

.task-overview__id {
  font-family: Consolas, "Courier New", monospace;
  font-size: 12px !important;
}

.is-success {
  color: var(--admin-success) !important;
}

.is-danger {
  color: var(--admin-danger) !important;
}

@media (max-width: 1100px) {
  .task-overview {
    grid-template-columns: 1fr 1fr;
  }

  .task-overview__metadata {
    grid-column: 1 / -1;
  }
}

@media (max-width: 720px) {
  .task-overview {
    grid-template-columns: 1fr;
  }

  .task-overview__metadata {
    grid-column: auto;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
