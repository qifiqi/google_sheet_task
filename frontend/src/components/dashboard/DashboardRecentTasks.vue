<script setup lang="ts">
import { computed } from 'vue'
import type { DashboardTask } from '../../types/api'
import { formatDateTime, taskStatusText, taskStatusType } from '../../utils/format'

const props = defineProps<{
  tasks: readonly DashboardTask[]
  checkedAt?: string | null
}>()

const emit = defineEmits<{
  view: [taskId: string]
}>()

const tableData = computed(() => [...props.tasks])
</script>

<template>
  <el-card shadow="never" class="recent-card">
    <template #header>
      <div class="card-header">
        <div>
          <strong>最近任务</strong>
          <span>{{ checkedAt ? `更新于 ${formatDateTime(checkedAt)}` : '等待数据' }}</span>
        </div>
        <el-link href="/admin/tasks" underline="never" type="primary">查看全部</el-link>
      </div>
    </template>

    <el-table :data="tableData" row-key="id" empty-text="暂无最近任务" class="recent-table">
      <el-table-column label="任务" min-width="220">
        <template #default="{ row }">
          <button class="task-link" type="button" @click="emit('view', row.id)">{{ row.name }}</button>
        </template>
      </el-table-column>
      <el-table-column prop="task_type" label="类型" min-width="145" show-overflow-tooltip />
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag size="small" :type="taskStatusType(row.status)">{{ taskStatusText(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="进度" width="132">
        <template #default="{ row }">
          <div class="task-progress">
            <el-progress :percentage="Number(row.progress_percentage || 0)" :show-text="false" />
            <span>{{ Math.round(Number(row.progress_percentage || 0)) }}%</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="创建时间" width="170">
        <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
      </el-table-column>
    </el-table>
  </el-card>
</template>

<style scoped>
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.card-header > div {
  display: grid;
  gap: 4px;
}

.card-header strong {
  color: var(--admin-text);
  font-size: 16px;
}

.card-header span {
  color: var(--admin-text-muted);
  font-size: 12px;
}

.recent-card :deep(.el-card__body) {
  padding: 0 20px 10px;
}

.recent-table {
  width: 100%;
}

.task-link {
  max-width: 100%;
  overflow: hidden;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--admin-text-regular);
  cursor: pointer;
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-link:hover {
  color: var(--admin-primary);
}

.task-progress {
  display: grid;
  grid-template-columns: minmax(60px, 1fr) 34px;
  align-items: center;
  gap: 8px;
}

.task-progress span {
  color: var(--admin-text-muted);
  font-size: 11px;
}
</style>
