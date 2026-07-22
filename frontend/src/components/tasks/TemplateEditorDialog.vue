<script setup lang="ts">
import { reactive, shallowRef, watch } from 'vue'
import { ElMessage } from 'element-plus'
import type { TaskTemplate } from '../../types/api'

const open = defineModel<boolean>({ default: false })
const props = defineProps<{ template: TaskTemplate | null; submitting: boolean }>()
const emit = defineEmits<{ save: [payload: { name: string; description: string; config: Record<string, unknown> }] }>()

const form = reactive({ name: '', description: '', config: '{}' })
const configError = shallowRef('')

watch([open, () => props.template], ([visible]) => {
  if (!visible) return
  form.name = props.template?.name || ''
  form.description = props.template?.description || ''
  form.config = JSON.stringify({
    ...(props.template?.config || {}),
    task_type: props.template?.config?.task_type || 'google_sheet',
  }, null, 2)
  configError.value = ''
}, { immediate: true })

function submit() {
  if (!form.name.trim()) {
    ElMessage.warning('请输入模板名称')
    return
  }
  try {
    const config = JSON.parse(form.config)
    if (!config || Array.isArray(config) || typeof config !== 'object') {
      throw new Error('配置必须是 JSON 对象')
    }
    configError.value = ''
    emit('save', { name: form.name.trim(), description: form.description.trim(), config })
  } catch (error) {
    configError.value = error instanceof Error ? error.message : '配置不是有效 JSON'
  }
}
</script>

<template>
  <el-dialog v-model="open" :title="template ? '编辑任务模板' : '新建任务模板'" width="min(680px, calc(100vw - 32px))" :close-on-click-modal="false">
    <el-form label-position="top" @submit.prevent="submit">
      <el-form-item label="模板名称" required><el-input v-model="form.name" maxlength="255" show-word-limit /></el-form-item>
      <el-form-item label="模板说明"><el-input v-model="form.description" type="textarea" :rows="2" maxlength="500" show-word-limit /></el-form-item>
      <el-form-item label="配置信息 (JSON)" required>
        <el-input v-model="form.config" class="template-editor__config" type="textarea" :rows="15" spellcheck="false" />
        <span v-if="configError" class="template-editor__error">{{ configError }}</span>
      </el-form-item>
    </el-form>
    <template #footer><el-button @click="open = false">取消</el-button><el-button type="primary" :loading="submitting" @click="submit">保存</el-button></template>
  </el-dialog>
</template>

<style scoped>
.template-editor__config :deep(textarea) { font-family: Consolas, "Courier New", monospace; font-size: 12px; line-height: 1.55; }
.template-editor__error { margin-top: 6px; color: var(--admin-danger); font-size: 12px; }
</style>
