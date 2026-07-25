<script setup lang="ts">
import { computed, onMounted, shallowRef } from 'vue'
import { Plus, Refresh } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import TemplateEditorDialog from '../../components/tasks/TemplateEditorDialog.vue'
import TemplateListTable from '../../components/tasks/TemplateListTable.vue'
import TemplatePreviewDialog from '../../components/tasks/TemplatePreviewDialog.vue'
import { requestJson } from '../../api/http'
import { useAuthStore } from '../../stores/auth'
import type { TaskTemplate } from '../../types/api'

const auth = useAuthStore()
const templates = shallowRef<TaskTemplate[]>([])
const loading = shallowRef(false)
const saving = shallowRef(false)
const errorMessage = shallowRef('')
const dialogVisible = shallowRef(false)
const editingTemplate = shallowRef<TaskTemplate | null>(null)
const previewTemplate = shallowRef<TaskTemplate | null>(null)
const previewVisible = shallowRef(false)
const keyword = shallowRef('')

const filteredTemplates = computed(() => {
  const query = keyword.value.trim().toLowerCase()
  return query ? templates.value.filter((item) => `${item.name} ${item.description || ''}`.toLowerCase().includes(query)) : templates.value
})
function canManage() { return auth.hasPermission('template:manage') }
function canUse() { return auth.hasPermission('task:create') }

async function loadTemplates() {
  loading.value = true; errorMessage.value = ''
  try { templates.value = (await requestJson<{ status: string; templates: TaskTemplate[] }>('/api/templates')).templates } catch (error) { errorMessage.value = error instanceof Error ? error.message : '加载模板失败' } finally { loading.value = false }
}
function openCreate() { editingTemplate.value = null; dialogVisible.value = true }
function openEdit(template: TaskTemplate) { editingTemplate.value = template; dialogVisible.value = true }
function duplicate(template: TaskTemplate) { editingTemplate.value = { ...template, id: 0, name: `${template.name} 副本` }; dialogVisible.value = true }
function openPreview(template: TaskTemplate) { previewTemplate.value = template; previewVisible.value = true }
function useTemplate(template: TaskTemplate) {
  const taskType = String(template.config.task_type || 'google_sheet').toLowerCase()
  if (!['google_sheet', 'google_sheet_c4', 'google_sheet_c5', 'google_sheet_c7'].includes(taskType)) {
    ElMessage.warning('当前任务类型暂不支持从旧创建页加载模板')
    return
  }
  const params = new URLSearchParams({ template_id: String(template.id) })
  const version = taskType.replace('google_sheet_', '')
  if (version && version !== 'google_sheet') params.set('version', version)
  window.location.assign(`/google-sheet/create?${params}`)
}
async function saveTemplate(payload: { name: string; description: string; config: Record<string, unknown> }) {
  saving.value = true
  try {
    const editing = editingTemplate.value
    await requestJson(editing?.id ? `/api/templates/${editing.id}` : '/api/templates', { method: editing?.id ? 'PUT' : 'POST', body: JSON.stringify(payload) })
    ElMessage.success(editing?.id ? '模板已更新' : '模板已创建'); dialogVisible.value = false; loadTemplates()
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '保存模板失败') } finally { saving.value = false }
}
async function removeTemplate(template: TaskTemplate) {
  await ElMessageBox.confirm(`确定删除模板“${template.name}”吗？`, '删除模板', { type: 'error', confirmButtonText: '删除' })
  await requestJson(`/api/templates/${template.id}`, { method: 'DELETE' }); ElMessage.success('模板已删除'); loadTemplates()
}
onMounted(loadTemplates)
</script>

<template>
  <section class="template-page">
    <header class="template-page__header"><div><p>任务模块</p><h1>任务模板</h1></div><el-button v-if="canManage()" type="primary" :icon="Plus" @click="openCreate">新建模板</el-button></header>
    <section class="template-page__panel">
      <div class="template-page__toolbar"><el-input v-model="keyword" clearable placeholder="搜索模板名称或说明" /><el-button text :icon="Refresh" aria-label="刷新模板列表" @click="loadTemplates" /></div>
      <el-alert v-if="errorMessage" :title="errorMessage" type="error" show-icon :closable="false" />
      <TemplateListTable
        :items="filteredTemplates"
        :loading="loading"
        :can-manage="canManage()"
        :can-use="canUse()"
        @edit="openEdit"
        @duplicate="duplicate"
        @remove="removeTemplate"
        @preview="openPreview"
        @use="useTemplate"
      />
    </section>
    <TemplateEditorDialog v-model="dialogVisible" :template="editingTemplate" :submitting="saving" @save="saveTemplate" />
    <TemplatePreviewDialog v-model="previewVisible" :template="previewTemplate" :can-use="canUse()" @use="useTemplate" />
  </section>
</template>

<style scoped>
.template-page { display: grid; gap: 16px; }.template-page__header { display: flex; align-items: end; justify-content: space-between; gap: 16px; }.template-page__header p { margin: 0 0 2px; color: var(--admin-text-muted); font-size: 13px; }.template-page__header h1 { margin: 0; color: var(--admin-text); font-size: 20px; font-weight: 600; }
.template-page__panel { display: grid; gap: 16px; padding: 16px 20px; border: 1px solid var(--admin-border); border-radius: var(--admin-radius); background: var(--admin-surface); }.template-page__toolbar { display: flex; align-items: center; gap: 8px; }.template-page__toolbar :deep(.el-input) { width: 260px; }
@media (max-width: 640px) { .template-page__toolbar :deep(.el-input) { width: 100%; } }
</style>
