<script setup lang="ts">
import { reactive, shallowRef, watch } from 'vue'
import { ElMessage } from 'element-plus'
import type { SchedulerTaskPayload, ScheduledTask } from '../../types/api'
import { scheduledFunctionOptions, scheduledTaskTypeOptions } from '../../utils/scheduler'
import '../../styles/scheduler/scheduler-dialog.css'

const open = defineModel<boolean>({ default: false })
const props = defineProps<{ task: ScheduledTask | null; submitting: boolean }>()
const emit = defineEmits<{ save: [payload: SchedulerTaskPayload] }>()

const form = reactive<SchedulerTaskPayload>({
  name: '', description: '', cron_expression: '0 0 * * *', task_type: 'cleanup',
  task_function: 'cleanup_old_data', task_params: '{\n  "days": 10\n}', is_active: true,
})
const paramsError = shallowRef('')

function resetForm(task: ScheduledTask | null) {
  form.name = task?.name || ''
  form.description = task?.description || ''
  form.cron_expression = task?.cron_expression || '0 0 * * *'
  form.task_type = task?.task_type || 'cleanup'
  form.task_function = task?.task_function || 'cleanup_old_data'
  form.task_params = JSON.stringify(task?.task_params || { days: 10 }, null, 2)
  form.is_active = task?.is_active ?? true
  paramsError.value = ''
}

watch([open, () => props.task], ([visible]) => { if (visible) resetForm(props.task) }, { immediate: true })

function submit() {
  if (!form.name.trim() || !form.cron_expression.trim() || !form.task_type || !form.task_function) {
    ElMessage.warning('请填写所有必填项')
    return
  }
  try {
    const params = form.task_params.trim() ? JSON.parse(form.task_params) : {}
    if (Array.isArray(params) || !params || typeof params !== 'object') throw new Error('参数必须是 JSON 对象')
    paramsError.value = ''
    emit('save', { ...form, name: form.name.trim(), description: form.description.trim(), cron_expression: form.cron_expression.trim(), task_params: JSON.stringify(params) })
  } catch (error) {
    paramsError.value = error instanceof Error ? error.message : '参数不是有效 JSON'
  }
}
</script>

<template>
  <el-dialog v-model="open" :title="task ? '编辑定时任务' : '新建定时任务'" width="min(720px, calc(100vw - 32px))" :close-on-click-modal="false">
    <el-form class="scheduler-dialog__form" label-position="top" @submit.prevent="submit">
      <div class="scheduler-dialog__form-grid">
        <el-form-item label="任务名称" required><el-input v-model="form.name" maxlength="255" show-word-limit /></el-form-item>
        <el-form-item label="任务类型" required><el-select v-model="form.task_type"><el-option v-for="item in scheduledTaskTypeOptions" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item>
      </div>
      <el-form-item label="任务说明"><el-input v-model="form.description" type="textarea" :rows="2" maxlength="500" show-word-limit /></el-form-item>
      <div class="scheduler-dialog__form-grid">
        <el-form-item label="Cron 表达式" required><el-input v-model="form.cron_expression" placeholder="0 0 * * *" /><span class="scheduler-dialog__hint">格式：分 时 日 月 周，例如每天零点为 `0 0 * * *`。</span></el-form-item>
        <el-form-item label="执行内容" required><el-select v-model="form.task_function"><el-option v-for="item in scheduledFunctionOptions" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item>
      </div>
      <el-form-item label="任务参数 (JSON)"><el-input v-model="form.task_params" class="scheduler-dialog__params" type="textarea" :rows="7" spellcheck="false" /><span v-if="paramsError" class="scheduler-dialog__error">{{ paramsError }}</span></el-form-item>
      <el-form-item><el-switch v-model="form.is_active" active-text="创建后立即启用" /></el-form-item>
    </el-form>
    <template #footer><el-button @click="open = false">取消</el-button><el-button type="primary" :loading="submitting" @click="submit">{{ task ? '保存修改' : '创建任务' }}</el-button></template>
  </el-dialog>
</template>
