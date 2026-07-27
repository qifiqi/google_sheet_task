<script setup lang="ts">
import { computed, reactive, shallowRef, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useStorage } from '@vueuse/core'
import { ArrowLeft, DocumentAdd, FolderChecked, Promotion, RefreshRight, Setting } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import GoogleSheetPicker from '../../components/google-sheet/GoogleSheetPicker.vue'
import ParameterMatrixEditor from '../../components/google-sheet/ParameterMatrixEditor.vue'
import ExecutionSettings from '../../components/google-sheet/ExecutionSettings.vue'
import { requestJson } from '../../api/http'
import { createEmptySheet, createParameterInputs, parseParameterInputs } from '../../utils/google-sheet-form'
import type { GoogleSheetCreateDraft } from '../../types/google-sheet'
import type { TaskItem, TaskTemplate } from '../../types/api'

const route = useRoute()
const router = useRouter()
const defaultDraft = (): GoogleSheetCreateDraft => ({
  taskName: '', description: '', sheet: createEmptySheet(),
  execution: { tokenType: 'file', tokenId: '', tokenFile: '', tokenJson: '', proxyUrl: '' },
  parameters: createParameterInputs(),
})
const storedDraft = useStorage<GoogleSheetCreateDraft>('google_sheet_c3_form_data', defaultDraft())
function cloneDraft(value: GoogleSheetCreateDraft) { return JSON.parse(JSON.stringify(value)) as GoogleSheetCreateDraft }
const draft = reactive<GoogleSheetCreateDraft>(cloneDraft(storedDraft.value))
const templates = shallowRef<TaskTemplate[]>([])
const selectedTemplateId = shallowRef<number>()
const loadingTemplates = shallowRef(false)
const submitting = shallowRef(false)
const saveTemplateVisible = shallowRef(false)
const templateName = shallowRef('')
const templateDescription = shallowRef('')
const savingTemplate = shallowRef(false)
const expandedConfigSections = shallowRef<string[]>([])

const combinationCount = computed(() => {
  try { const groups = parseParameterInputs(draft.parameters); return groups.length ? groups.reduce((total, item) => total * item.length, 1) : 0 } catch { return 0 }
})

function copyConfig(config: Record<string, unknown>, name = '', description = '') {
  draft.taskName = name || String(config.base_task_name || '')
  draft.description = description || String(config.task_description || '')
  draft.sheet = {
    spreadsheetId: String(config.spreadsheet_id || ''), title: String(config.title || config.spreadsheet_title || ''), sheetName: String(config.sheet_name || ''),
  }
  draft.execution = {
    tokenType: config.token_type === 'json' ? 'json' : 'file', tokenId: String(config.token_id || ''), tokenFile: String(config.token_file || ''), tokenJson: String(config.token_json || ''), proxyUrl: String(config.proxy_url || ''),
  }
  const values = Array.isArray(config.parameters) ? config.parameters : []
  draft.parameters = Array.from({ length: 6 }, (_, index) => values[index] ? JSON.stringify(values[index]) : '')
}

async function loadTemplates() {
  loadingTemplates.value = true
  try {
    const payload = await requestJson<{ status: string; templates: TaskTemplate[] }>('/api/templates')
    templates.value = (payload.templates || []).filter((item) => !item.config.task_type || String(item.config.task_type).toLowerCase() === 'google_sheet')
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '加载模板失败') } finally { loadingTemplates.value = false }
}

async function loadTemplate(templateId: number | null) {
  if (!templateId) return
  try {
    const template = await requestJson<TaskTemplate>(`/api/templates/${templateId}`)
    copyConfig(template.config, template.name, template.description || '')
    ElMessage.success('模板已应用')
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '加载模板失败') }
}

async function loadRestart(taskId: string) {
  try {
    const payload = await requestJson<{ status: string; task: TaskItem }>(`/api/tasks/${encodeURIComponent(taskId)}`)
    copyConfig(payload.task.config || {}, `${payload.task.name} (重启)`, payload.task.description || '')
    ElMessage.success('已加载原任务配置')
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '加载重启配置失败') }
}

function buildConfig() {
  if (!draft.sheet.spreadsheetId || !draft.sheet.sheetName) throw new Error('请选择 Google Sheet 和工作表')
  const parameters = parseParameterInputs(draft.parameters)
  if (!parameters.length) throw new Error('请至少填写一组参数')
  if (draft.execution.tokenType === 'json' && !draft.execution.tokenJson.trim()) throw new Error('请输入 Token JSON')
  return {
    spreadsheet_id: draft.sheet.spreadsheetId, title: draft.sheet.title || null, sheet_name: draft.sheet.sheetName,
    token_type: draft.execution.tokenType, token_id: draft.execution.tokenType === 'file' ? draft.execution.tokenId || null : null,
    token_file: draft.execution.tokenFile || null, token_json: draft.execution.tokenType === 'json' ? draft.execution.tokenJson : null,
    proxy_url: draft.execution.proxyUrl || null, parameters,
  }
}

async function submit() {
  try {
    if (!draft.taskName.trim()) throw new Error('请输入任务名称')
    const config = buildConfig()
    submitting.value = true
    const response = await requestJson<{ status: string; task_id: string; message?: string }>('/api/tasks', {
      method: 'POST', body: JSON.stringify({ name: draft.taskName.trim(), description: draft.description.trim() || `执行 ${combinationCount.value} 个参数组合`, task_type: 'google_sheet', config }),
    })
    storedDraft.value = defaultDraft()
    ElMessage.success(response.message || 'C3 任务已创建并启动')
    window.setTimeout(() => { void router.push({ name: 'C3TaskDetail', params: { taskId: response.task_id } }) }, 500)
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '创建任务失败') } finally { submitting.value = false }
}

async function clearDraft() {
  await ElMessageBox.confirm('确定清除当前草稿吗？', '清除草稿', { type: 'warning', confirmButtonText: '清除' })
  Object.assign(draft, defaultDraft()); storedDraft.value = defaultDraft(); selectedTemplateId.value = undefined
}

function returnToTaskList() { void router.push({ name: 'C3Tasks' }) }

function openSaveTemplate() { templateName.value = draft.taskName ? `${draft.taskName} 模板` : ''; templateDescription.value = draft.description; saveTemplateVisible.value = true }
async function saveTemplate() {
  try {
    if (!templateName.value.trim()) throw new Error('请输入模板名称')
    savingTemplate.value = true
    await requestJson('/api/templates', { method: 'POST', body: JSON.stringify({ name: templateName.value.trim(), description: templateDescription.value.trim(), config: { ...buildConfig(), task_type: 'google_sheet' } }) })
    saveTemplateVisible.value = false; ElMessage.success('模板已保存'); loadTemplates()
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '保存模板失败') } finally { savingTemplate.value = false }
}

watch(draft, (value) => { storedDraft.value = cloneDraft(value) }, { deep: true })
loadTemplates()
const templateId = Number(route.query.template_id)
const restartTaskId = typeof route.query.restart_task_id === 'string' ? route.query.restart_task_id : ''
if (templateId) { selectedTemplateId.value = templateId; loadTemplate(templateId) } else if (restartTaskId) loadRestart(restartTaskId)
</script>

<template>
  <section class="create-page">
    <header class="create-page__header"><div><p>业务模块 / Google Sheet</p><h1>创建 C3 任务</h1></div><el-button :icon="ArrowLeft" @click="returnToTaskList">返回任务列表</el-button></header>
    <el-form class="create-page__form" label-position="top" @submit.prevent>
      <section class="create-page__section"><header class="create-page__section-header"><div><h2>任务信息</h2><p>填写任务名称，或从已保存的 C3 模板恢复参数。</p></div></header><div class="create-page__fields create-page__fields--meta"><el-form-item label="任务模板"><el-select v-model="selectedTemplateId" clearable filterable :loading="loadingTemplates" placeholder="不使用模板" @change="loadTemplate"><el-option v-for="template in templates" :key="template.id" :label="template.name" :value="template.id" /></el-select></el-form-item><el-form-item label="任务名称" required><el-input v-model="draft.taskName" placeholder="例如：策略验证-2026-07" /></el-form-item><el-form-item label="任务描述"><el-input v-model="draft.description" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }" placeholder="可选，记录任务用途" /></el-form-item></div></section>
      <section class="create-page__section"><header class="create-page__section-header"><div><h2>Google Sheet 配置</h2><p>选择当前可用的资源，并加载要执行的工作表。</p></div></header><GoogleSheetPicker v-model="draft.sheet" :proxy-url="draft.execution.proxyUrl" /><el-collapse v-model="expandedConfigSections" class="create-page__execution-collapse"><el-collapse-item name="execution"><template #title><div class="create-page__execution-collapse-title"><el-icon><Setting /></el-icon><div><strong>执行配置</strong><span>Token、认证方式和代理</span></div></div></template><ExecutionSettings v-model="draft.execution" :show-header="false" /></el-collapse-item></el-collapse></section>
      <section class="create-page__section"><ParameterMatrixEditor v-model="draft.parameters" /></section>
      <footer class="create-page__actions"><div><el-tag type="info" effect="plain">预计 {{ combinationCount }} 个参数组合</el-tag></div><div class="create-page__action-buttons"><el-button :icon="RefreshRight" @click="clearDraft">清除草稿</el-button><el-button :icon="FolderChecked" @click="openSaveTemplate">保存模板</el-button><el-button type="primary" :icon="Promotion" :loading="submitting" @click="submit">创建并执行</el-button></div></footer>
    </el-form>
    <el-dialog v-model="saveTemplateVisible" title="保存 C3 模板" width="420px"><el-form label-position="top"><el-form-item label="模板名称" required><el-input v-model="templateName" /></el-form-item><el-form-item label="模板描述"><el-input v-model="templateDescription" type="textarea" :rows="3" /></el-form-item></el-form><template #footer><el-button @click="saveTemplateVisible = false">取消</el-button><el-button type="primary" :loading="savingTemplate" @click="saveTemplate"><el-icon><DocumentAdd /></el-icon>保存</el-button></template></el-dialog>
  </section>
</template>

<style scoped>
.create-page { display: grid; gap: 16px; max-width: 1440px; margin: 0 auto; }.create-page__header { display: flex; align-items: end; justify-content: space-between; gap: 16px; }.create-page__header p { margin: 0 0 2px; color: var(--admin-text-muted); font-size: 13px; }.create-page__header h1 { margin: 0; color: var(--admin-text); font-size: 20px; font-weight: 600; }.create-page__form { display: grid; gap: 16px; }.create-page__section { display: grid; gap: 16px; padding: 20px; border: 1px solid var(--admin-border); border-radius: var(--admin-radius); background: var(--admin-surface); }.create-page__section-header { display: flex; align-items: start; justify-content: space-between; }.create-page__section h2 { margin: 0; color: var(--admin-text); font-size: 16px; font-weight: 600; }.create-page__section p { margin: 4px 0 0; color: var(--admin-text-muted); font-size: 13px; }.create-page__fields { display: grid; gap: 16px; }.create-page__fields--meta { grid-template-columns: minmax(180px, 0.8fr) minmax(220px, 1fr) minmax(260px, 1.3fr); }.create-page__fields :deep(.el-form-item) { margin-bottom: 0; }.create-page__execution-collapse { border-top: 1px solid var(--admin-border-light); border-bottom: 1px solid var(--admin-border-light); }.create-page__execution-collapse :deep(.el-collapse-item__header) { height: 56px; border-bottom: 0; background: transparent; }.create-page__execution-collapse :deep(.el-collapse-item__wrap) { border-bottom: 0; background: transparent; }.create-page__execution-collapse :deep(.el-collapse-item__content) { padding-bottom: 16px; }.create-page__execution-collapse-title { display: flex; align-items: center; gap: 10px; }.create-page__execution-collapse-title > .el-icon { color: var(--admin-primary); font-size: 18px; }.create-page__execution-collapse-title div { display: grid; gap: 1px; }.create-page__execution-collapse-title strong { color: var(--admin-text); font-size: 14px; font-weight: 600; }.create-page__execution-collapse-title span { color: var(--admin-text-muted); font-size: 12px; }.create-page__actions { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 16px 20px; border: 1px solid var(--admin-border); border-radius: var(--admin-radius); background: var(--admin-surface); }.create-page__action-buttons { display: flex; flex-wrap: wrap; justify-content: end; gap: 8px; }@media (max-width: 900px) { .create-page__fields--meta { grid-template-columns: 1fr 1fr; }.create-page__fields--meta :deep(.el-form-item:last-child) { grid-column: 1 / -1; } }@media (max-width: 640px) { .create-page__header,.create-page__actions { align-items: stretch; flex-direction: column; }.create-page__fields--meta { grid-template-columns: 1fr; }.create-page__fields--meta :deep(.el-form-item:last-child) { grid-column: auto; }.create-page__action-buttons { justify-content: stretch; }.create-page__action-buttons :deep(.el-button) { flex: 1; }.create-page__section { padding: 16px; } }
</style>
