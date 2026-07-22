<script setup lang="ts">
import { Delete, EditPen, MoreFilled, Promotion, VideoPause, VideoPlay } from '@element-plus/icons-vue'
import type { ScheduledTask } from '../../types/api'
import { formatDateTime } from '../../utils/format'
import { scheduledFunctionText, scheduledTaskStatus, scheduledTaskStatusType, scheduledTaskTypeText } from '../../utils/scheduler'

defineProps<{ tasks: ScheduledTask[]; loading: boolean; canManage: boolean }>()
const emit = defineEmits<{ edit: [task: ScheduledTask]; toggle: [task: ScheduledTask]; run: [task: ScheduledTask]; remove: [task: ScheduledTask] }>()
</script>

<template>
  <el-table v-loading="loading" :data="tasks" class="scheduler-task-table" empty-text="暂无定时任务">
    <el-table-column prop="id" label="ID" width="78" />
    <el-table-column label="任务" min-width="220"><template #default="{ row }"><div class="scheduler-task-table__name"><el-tooltip :content="row.name" placement="top"><strong>{{ row.name }}</strong></el-tooltip><span>{{ row.description || '未填写说明' }}</span></div></template></el-table-column>
    <el-table-column label="Cron 表达式" width="156"><template #default="{ row }"><code class="scheduler-task-table__cron">{{ row.cron_expression }}</code></template></el-table-column>
    <el-table-column label="任务类型" width="128"><template #default="{ row }"><el-tag type="info" effect="plain">{{ scheduledTaskTypeText(row.task_type) }}</el-tag></template></el-table-column>
    <el-table-column label="执行内容" min-width="144"><template #default="{ row }">{{ scheduledFunctionText(row.task_function) }}</template></el-table-column>
    <el-table-column label="状态" width="96"><template #default="{ row }"><el-tag :type="scheduledTaskStatusType(row)">{{ scheduledTaskStatus(row) }}</el-tag></template></el-table-column>
    <el-table-column prop="run_count" label="执行次数" width="104" align="right" />
    <el-table-column label="上次执行" width="178"><template #default="{ row }">{{ formatDateTime(row.last_run_time) }}</template></el-table-column>
    <el-table-column label="下次执行" width="178"><template #default="{ row }">{{ formatDateTime(row.next_run_time) }}</template></el-table-column>
    <el-table-column v-if="canManage" fixed="right" label="操作" width="188"><template #default="{ row }"><div class="scheduler-task-table__actions"><el-button link type="primary" :icon="EditPen" @click="emit('edit', row)">编辑</el-button><el-tooltip :disabled="row.is_active" content="请先启用任务"><el-button link type="primary" :icon="Promotion" :disabled="!row.is_active" @click="emit('run', row)">执行</el-button></el-tooltip><el-dropdown trigger="click" @command="(command) => emit(command, row)"><el-button link :icon="MoreFilled" aria-label="更多定时任务操作" /><template #dropdown><el-dropdown-menu><el-dropdown-item command="toggle"><el-icon><component :is="row.is_active ? VideoPause : VideoPlay" /></el-icon>{{ row.is_active ? '停用任务' : '启用任务' }}</el-dropdown-item><el-dropdown-item command="remove" divided><el-icon><Delete /></el-icon>删除任务</el-dropdown-item></el-dropdown-menu></template></el-dropdown></div></template></el-table-column>
  </el-table>
</template>
