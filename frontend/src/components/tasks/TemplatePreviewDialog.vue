<script setup lang="ts">
import { computed } from 'vue'
import type { TaskTemplate } from '../../types/api'
import { templateOverview, templateTaskTypeText } from '../../utils/task'

const open = defineModel<boolean>({ default: false })
const props = defineProps<{ template: TaskTemplate | null; canUse: boolean }>()
const emit = defineEmits<{ use: [template: TaskTemplate] }>()

const overview = computed(() => props.template ? templateOverview(props.template.config) : null)
const configText = computed(() => JSON.stringify(props.template?.config || {}, null, 2))
const taskType = computed(() => templateTaskTypeText(typeof props.template?.config.task_type === 'string' ? props.template.config.task_type : undefined))
</script>

<template>
  <el-dialog v-model="open" title="模板预览" width="min(680px, calc(100vw - 32px))">
    <template v-if="template">
      <el-descriptions :column="2" border class="template-preview__summary">
        <el-descriptions-item label="模板名称" :span="2">{{ template.name }}</el-descriptions-item>
        <el-descriptions-item label="任务类型">{{ taskType }}</el-descriptions-item>
        <el-descriptions-item label="参数规模">{{ overview?.parameterLabel }}</el-descriptions-item>
        <el-descriptions-item label="Sheet 资源">{{ overview?.sheetLabel }}</el-descriptions-item>
        <el-descriptions-item label="标的">{{ overview?.stockLabel }}</el-descriptions-item>
        <el-descriptions-item label="模板说明" :span="2">{{ template.description || '未填写说明' }}</el-descriptions-item>
      </el-descriptions>
      <section class="template-preview__config"><h3>配置预览</h3><pre>{{ configText }}</pre></section>
    </template>
    <template #footer><el-button @click="open = false">关闭</el-button><el-button v-if="template && canUse" type="primary" @click="emit('use', template)">使用此模板</el-button></template>
  </el-dialog>
</template>

<style scoped>
.template-preview__summary { margin-bottom: 16px; }
.template-preview__config { display: grid; gap: 8px; }
.template-preview__config h3 { margin: 0; color: var(--admin-text); font-size: 16px; font-weight: 600; }
.template-preview__config pre { max-height: 360px; margin: 0; padding: 14px; overflow: auto; border: 1px solid var(--admin-border-light); border-radius: 6px; background: var(--admin-bg); color: var(--admin-text-regular); font: 12px/1.6 Consolas, "Courier New", monospace; white-space: pre-wrap; word-break: break-word; }
</style>
