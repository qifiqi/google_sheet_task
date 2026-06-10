<template>
  <div class="task-actions">
    <el-button
      v-if="task.status === 'running'"
      type="warning"
      size="small"
      text
      @click.stop="handleCancel"
    >
      停止
    </el-button>
    <el-button
      v-if="task.status === 'error' || task.status === 'cancelled'"
      type="primary"
      size="small"
      text
      @click.stop="handleRestart"
    >
      重启
    </el-button>
    <el-popconfirm title="确定删除此任务？" @confirm="handleDelete">
      <template #reference>
        <el-button type="danger" size="small" text @click.stop>删除</el-button>
      </template>
    </el-popconfirm>
  </div>
</template>

<script setup>
import { cancelTask, restartTask, deleteTask } from '@/api/task'
import { ElMessage } from 'element-plus'

const props = defineProps({
  task: { type: Object, required: true },
})

const emit = defineEmits(['refresh'])

async function handleCancel() {
  try {
    await cancelTask(props.task.id)
    ElMessage.success('任务已停止')
    emit('refresh')
  } catch { ElMessage.error('停止失败') }
}

async function handleRestart() {
  try {
    await restartTask(props.task.id)
    ElMessage.success('任务已重启')
    emit('refresh')
  } catch { ElMessage.error('重启失败') }
}

async function handleDelete() {
  try {
    await deleteTask(props.task.id)
    ElMessage.success('任务已删除')
    emit('refresh')
  } catch { ElMessage.error('删除失败') }
}
</script>

<style lang="scss" scoped>
.task-actions {
  display: flex;
  gap: 4px;
  align-items: center;
  flex-wrap: nowrap;
}
</style>
