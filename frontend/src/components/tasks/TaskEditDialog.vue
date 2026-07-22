<script setup lang="ts">
import { reactive, shallowRef, watch } from 'vue'
import { ElMessage } from 'element-plus'
import type { TaskItem } from '../../types/api'

const open = defineModel<boolean>({ default: false })
const props = defineProps<{ task: TaskItem | null; submitting: boolean }>()
const emit = defineEmits<{
  save: [payload: { id: string; name: string; description: string; status: string; config: Record<string, unknown> }]
}>()

const form = reactive({ name: '', description: '', status: 'pending', config: '{}' })
const configError = shallowRef('')
const editableStatuses = [
  { label: '待执行', value: 'pending' },
  { label: '已完成', value: 'completed' },
  { label: '已取消', value: 'cancelled' },
  { label: '执行出错', value: 'error' },
]

watch([open, () => props.task], ([visible]) => {
  if (!visible || !props.task) return
  form.name = props.task.name || ''
  form.description = props.task.description || ''
  form.status = editableStatuses.some(item => item.value === props.task?.status) ? props.task.status : 'pending'
  form.config = JSON.stringify(props.task.config || {}, null, 2)
  configError.value = ''
}, { immediate: true })

function submit() {
  if (!props.task || !form.name.trim()) {
    ElMessage.warning('请输入任务名称')
    return
  }
  try {
    const config = JSON.parse(form.config)
    if (!config || Array.isArray(config) || typeof config !== 'object') {
      throw new Error('配置必须是 JSON 对象')
    }
    configError.value = ''
    emit('save', {
      id: props.task.id,
      name: form.name.trim(),
      description: form.description.trim(),
      status: form.status,
      config,
    })
  } catch (error) {
    configError.value = error instanceof Error ? error.message : '配置不是有效 JSON'
  }
}
</script>

<template>
  <el-dialog v-model="open" title="编辑任务" width="min(720px, calc(100vw - 32px))" :close-on-click-modal="!submitting" :close-on-press-escape="!submitting">
    <el-form label-position="top" @submit.prevent="submit">
      <div class="task-edit-dialog__identity">
        <el-form-item label="任务名称" required><el-input v-model="form.name" maxlength="255" show-word-limit /></el-form-item>
        <el-form-item label="任务状态"><el-select v-model="form.status"><el-option v-for="item in editableStatuses" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item>
      </div>
      <el-form-item label="任务说明"><el-input v-model="form.description" type="textarea" :rows="2" maxlength="500" show-word-limit /></el-form-item>
      <el-form-item label="配置信息 (JSON)" required>
        <el-input v-model="form.config" class="task-edit-dialog__config" type="textarea" :rows="16" spellcheck="false" />
        <span v-if="configError" class="task-edit-dialog__error">{{ configError }}</span>
      </el-form-item>
    </el-form>
    <template #footer><el-button :disabled="submitting" @click="open = false">取消</el-button><el-button type="primary" :loading="submitting" @click="submit">保存</el-button></template>
  </el-dialog>
</template>

<style scoped>
.task-edit-dialog__identity { display: grid; grid-template-columns: minmax(0, 1fr) 180px; gap: 16px; }
.task-edit-dialog__config :deep(textarea) { font-family: Consolas, "Courier New", monospace; font-size: 12px; line-height: 1.55; }
.task-edit-dialog__error { margin-top: 6px; color: var(--admin-danger); font-size: 12px; }
@media (max-width: 640px) { .task-edit-dialog__identity { grid-template-columns: 1fr; gap: 0; } }
</style>
