<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, reactive, shallowRef, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useStorage } from '@vueuse/core'
import { ArrowLeft, CirclePlus, FolderChecked, Promotion, RefreshRight, Setting, WarningFilled } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import TaskTemplateSelect from '../../components/google-sheet/TaskTemplateSelect.vue'
import GoogleSheetPicker from '../../components/google-sheet/GoogleSheetPicker.vue'
import ParameterMatrixEditor from '../../components/google-sheet/ParameterMatrixEditor.vue'
import DatePickerField from '../../components/google-sheet/DatePickerField.vue'
import { useDebouncedDraftStorage } from '../../composables/useDebouncedDraftStorage'
import { useTaskTemplates } from '../../composables/useTaskTemplates'
import { requestJson } from '../../api/http'
import { c31CombinationCount, createEmptySheet, createParameterInputs, parseC31SheetTitle, parseParameterInputs } from '../../utils/google-sheet-form'
import type { C31CreateDraft, GoogleSheetSelection } from '../../types/google-sheet'
import type { C31BatchCreateResponse, TaskItem, TaskTemplate } from '../../types/api'

const loadExecutionSettings = () => import('../../components/google-sheet/ExecutionSettings.vue')
const ExecutionSettings = defineAsyncComponent(loadExecutionSettings)
const C31BatchResultDialog = defineAsyncComponent(() => import('../../components/google-sheet/C31BatchResultDialog.vue'))

const route = useRoute()
const router = useRouter()
const defaultDraft = (): C31CreateDraft => ({ taskName: '', description: '', stockCode: '', marketType: 'cn', priceMode: 'vwap_price', klineAdjustment: 'forward', endDate: '', sheets: [createEmptySheet()], execution: { tokenType: 'file', tokenId: '', tokenFile: '', tokenJson: '', proxyUrl: '' }, parameters: createParameterInputs() })
const storedDraft = useStorage<C31CreateDraft>('google_sheet_c31_form_data', defaultDraft())
function cloneDraft(value: C31CreateDraft) { return JSON.parse(JSON.stringify(value)) as C31CreateDraft }
const draft = reactive<C31CreateDraft>(cloneDraft(storedDraft.value))
const { templates, loading: loadingTemplates, loadTemplates: loadAvailableTemplates } = useTaskTemplates('google_sheet_c31')
const templateOptions = computed(() => templates.value.map((template) => ({ label: template.name, value: template.id })))
const selectedTemplateId = shallowRef<number>()
const submitting = shallowRef(false)
const savingTemplate = shallowRef(false)
const saveTemplateVisible = shallowRef(false)
const templateName = shallowRef('')
const templateDescription = shallowRef('')
const expandedConfigSections = shallowRef<string[]>([])
const executionSettingsMounted = shallowRef(false)
const batchResultVisible = shallowRef(false)
const batchResult = shallowRef<C31BatchCreateResponse | null>(null)

const parsedParameters = computed(() => { try { return parseParameterInputs(draft.parameters, true) } catch { return [] } })
const parameterCount = computed(() => parsedParameters.value.length ? c31CombinationCount(parsedParameters.value) : 0)
const titleGroups = computed(() => {
  const groups = new Map<string, GoogleSheetSelection[]>()
  for (const sheet of draft.sheets) {
    const parsed = parseC31SheetTitle(sheet.title)
    if (!parsed) continue
    const group = groups.get(parsed.year)
    if (group) group.push(sheet)
    else groups.set(parsed.year, [sheet])
  }
  return groups
})
const validationError = computed(() => {
  if (!parameterCount.value) return '请填写至少一组有效参数'
  if (!draft.sheets.length || draft.sheets.some((sheet) => !sheet.spreadsheetId || !sheet.sheetName || !sheet.title)) return '请完善所有 Google Sheet 配置'
  if (draft.sheets.some((sheet) => !parseC31SheetTitle(sheet.title))) return '表标题须以“任意前缀-数字y-数字]”结尾，例如 策略A-1y-3]'
  if ([...titleGroups.value.values()].some((sheets) => sheets.length !== parameterCount.value)) return `每个年份组的 Sheet 数必须等于 ${parameterCount.value} 个参数组合`
  return ''
})
const estimatedChildren = computed(() => validationError.value ? 0 : parameterCount.value * titleGroups.value.size)

function applyConfig(config: Record<string, unknown>, name = '', description = '') {
  const sheets = Array.isArray(config.sheets) ? config.sheets : []
  const parameters = Array.isArray(config.parameters) ? config.parameters : []
  const nextDraft: C31CreateDraft = {
    taskName: name || String(config.base_task_name || ''),
    description: description || String(config.task_description || ''),
    stockCode: String((Array.isArray(config.stock_codes) ? config.stock_codes[0] : config.stock_code) || ''),
    marketType: config.market_type === 'en' ? 'en' : 'cn',
    priceMode: ['kp_price', 'sp_price'].includes(String(config.price_mode)) ? config.price_mode as C31CreateDraft['priceMode'] : 'vwap_price',
    klineAdjustment: ['back', 'none'].includes(String(config.kline_adjustment)) ? config.kline_adjustment as C31CreateDraft['klineAdjustment'] : 'forward',
    endDate: String(config.end_date || ''),
    sheets: sheets.length ? sheets.map((item) => { const sheet = item as Record<string, unknown>; return { spreadsheetId: String(sheet.spreadsheet_id || ''), title: String(sheet.title || ''), sheetName: String(sheet.sheet_name || '') } }) : [createEmptySheet()],
    execution: { tokenType: config.token_type === 'json' ? 'json' : 'file', tokenId: String(config.token_id || ''), tokenFile: String(config.token_file || ''), tokenJson: String(config.token_json || ''), proxyUrl: String(config.proxy_url || '') },
    parameters: Array.from({ length: 6 }, (_, index) => parameters[index] ? JSON.stringify(parameters[index]) : ''),
  }
  Object.assign(draft, nextDraft)
}
async function loadTemplates(force = false) { try { await loadAvailableTemplates(force) } catch (error) { ElMessage.error(error instanceof Error ? error.message : '加载模板失败') } }
async function loadTemplate(id: number | null) { if (!id) return; try { let cachedTemplate = templates.value.find((item) => item.id === id); if (!cachedTemplate) { await loadTemplates(); cachedTemplate = templates.value.find((item) => item.id === id) } const template = cachedTemplate ?? await requestJson<TaskTemplate>(`/api/templates/${id}`); applyConfig(template.config, template.name, template.description || ''); ElMessage.success('模板已应用') } catch (error) { ElMessage.error(error instanceof Error ? error.message : '加载模板失败') } }
function scheduleTemplateApply(templateId: number | undefined) { if (!templateId) return; requestAnimationFrame(() => { window.setTimeout(() => { void loadTemplate(templateId) }, 0) }) }
async function loadRestart(taskId: string) { try { const payload = await requestJson<{ status: string; task: TaskItem }>(`/api/tasks/${encodeURIComponent(taskId)}`); applyConfig(payload.task.config || {}, `${payload.task.name} (重启)`, payload.task.description || ''); ElMessage.success('已加载原任务配置') } catch (error) { ElMessage.error(error instanceof Error ? error.message : '加载重启配置失败') } }
function buildConfig() { if (!draft.taskName.trim()) throw new Error('请输入任务 Base Name'); if (!draft.stockCode.trim()) throw new Error('请输入股票代码'); if (validationError.value) throw new Error(validationError.value); if (draft.execution.tokenType === 'file' && !draft.execution.tokenId.trim()) throw new Error('请选择 Token'); if (draft.execution.tokenType === 'json' && !draft.execution.tokenJson.trim()) throw new Error('请输入 Token JSON'); return { base_task_name: draft.taskName.trim(), task_description: draft.description.trim(), stock_codes: [draft.stockCode.trim().toUpperCase()], market_type: draft.marketType, price_mode: draft.priceMode, kline_adjustment: draft.klineAdjustment, end_date: draft.endDate || undefined, token_type: draft.execution.tokenType, token_id: draft.execution.tokenType === 'file' ? draft.execution.tokenId || null : null, token_file: draft.execution.tokenFile || null, token_json: draft.execution.tokenType === 'json' ? draft.execution.tokenJson : null, proxy_url: draft.execution.proxyUrl || null, parameter_dimensions: parsedParameters.value.map((_, index) => index + 1), parameters: parsedParameters.value, sheets: draft.sheets.map((sheet) => ({ spreadsheet_id: sheet.spreadsheetId, title: sheet.title, sheet_name: sheet.sheetName })) } }
function addSheet() { draft.sheets.push(createEmptySheet()) }
function removeSheet(index: number) { if (draft.sheets.length > 1) draft.sheets.splice(index, 1) }
async function submit() { try { const config = buildConfig(); submitting.value = true; const response = await requestJson<C31BatchCreateResponse>('/api/tasks/batch-create', { method: 'POST', body: JSON.stringify({ name: draft.taskName.trim(), description: draft.description.trim(), task_type: 'google_sheet_c31', config }) }); Object.assign(draft, defaultDraft()); storedDraft.value = defaultDraft(); batchResult.value = response; batchResultVisible.value = true; ElMessage.success(response.message || `已创建 ${response.total_created} 个 C3 子任务`) } catch (error) { ElMessage.error(error instanceof Error ? error.message : '批量创建失败') } finally { submitting.value = false } }
function viewChildTask(taskId: string) { batchResultVisible.value = false; void router.push({ name: 'C3TaskDetail', params: { taskId } }) }
function viewChildTasks() { batchResultVisible.value = false; void router.push({ name: 'C3Tasks' }) }
async function clearDraft() { await ElMessageBox.confirm('确定清除当前批量草稿吗？', '清除草稿', { type: 'warning', confirmButtonText: '清除' }); Object.assign(draft, defaultDraft()); storedDraft.value = defaultDraft(); selectedTemplateId.value = undefined }
function returnToTaskList() { void router.push({ name: 'C3Tasks' }) }
function openSaveTemplate() { templateName.value = draft.taskName ? `${draft.taskName} 模板` : ''; templateDescription.value = draft.description; saveTemplateVisible.value = true }
async function saveTemplate() { try { if (!templateName.value.trim()) throw new Error('请输入模板名称'); savingTemplate.value = true; await requestJson('/api/templates', { method: 'POST', body: JSON.stringify({ name: templateName.value.trim(), description: templateDescription.value.trim(), config: { ...buildConfig(), task_type: 'google_sheet_c31' } }) }); saveTemplateVisible.value = false; ElMessage.success('模板已保存'); loadTemplates(true) } catch (error) { ElMessage.error(error instanceof Error ? error.message : '保存模板失败') } finally { savingTemplate.value = false } }
watch(expandedConfigSections, (sections) => {
  if (sections.includes('execution')) executionSettingsMounted.value = true
})
useDebouncedDraftStorage(draft, storedDraft, cloneDraft)
onMounted(() => {
  const prefetch = () => { void loadExecutionSettings() }
  if (typeof window.requestIdleCallback === 'function') window.requestIdleCallback(prefetch, { timeout: 1200 })
  else window.setTimeout(prefetch, 300)
})
loadTemplates(); const templateId = Number(route.query.template_id); const restartTaskId = typeof route.query.restart_task_id === 'string' ? route.query.restart_task_id : ''; if (templateId) { selectedTemplateId.value = templateId; loadTemplate(templateId) } else if (restartTaskId) loadRestart(restartTaskId)
</script>

<template>
  <section class="c31-page">
    <header class="c31-page__header"><div><p>业务模块 / Google Sheet</p><h1>创建 C31 批量任务</h1></div><el-button :icon="ArrowLeft" @click="returnToTaskList">返回任务列表</el-button></header>
    <el-form class="c31-page__form" label-position="top" @submit.prevent>
      <section class="c31-page__section">
        <header class="c31-page__section-header"><div><h2>批次信息</h2><p>一个批次会按股票、参数组合及年份组拆分为可独立执行的 C3 子任务。</p></div></header>
        <div class="c31-page__meta-grid">
          <el-form-item label="任务模板"><TaskTemplateSelect v-model="selectedTemplateId" :options="templateOptions" :loading="loadingTemplates" @change="scheduleTemplateApply" /></el-form-item>
          <el-form-item label="任务 Base Name" required><el-input v-model="draft.taskName" placeholder="例如：strategy_batch" /></el-form-item>
          <el-form-item label="股票代码" required><el-input v-model="draft.stockCode" placeholder="例如：601727" /></el-form-item>
          <el-form-item label="市场"><el-radio-group v-model="draft.marketType"><el-radio-button value="cn">A股</el-radio-button><el-radio-button value="en">美股</el-radio-button></el-radio-group></el-form-item>
          <el-form-item label="价格类型"><el-segmented v-model="draft.priceMode" :options="[{ label: '加权平均价', value: 'vwap_price' }, { label: '开盘价', value: 'kp_price' }, { label: '收盘价', value: 'sp_price' }]" /></el-form-item>
          <el-form-item label="K 线复权"><el-segmented v-model="draft.klineAdjustment" :options="[{ label: '前复权', value: 'forward' }, { label: '后复权', value: 'back' }, { label: '不复权', value: 'none' }]" /></el-form-item>
          <el-form-item label="结束日期"><DatePickerField v-model="draft.endDate" type="date" value-format="YYYY-MM-DD" placeholder="按后端默认逻辑" /></el-form-item>
          <el-form-item class="c31-page__description" label="任务描述"><el-input v-model="draft.description" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }" placeholder="可选，记录这批任务的用途" /></el-form-item>
        </div>
      </section>
      <section class="c31-page__section"><header class="c31-page__section-header"><div><h2>Sheet 对齐矩阵</h2><p>同一年份组内的 Sheet 数必须等于参数组合数，标题格式为“任意前缀-数字y-数字]”。</p></div><el-button :icon="CirclePlus" @click="addSheet">添加 Sheet</el-button></header><div class="c31-page__sheets"><GoogleSheetPicker v-for="(_sheet, index) in draft.sheets" :key="index" v-model="draft.sheets[index]" :index="index" :removable="draft.sheets.length > 1" :proxy-url="draft.execution.proxyUrl" @remove="removeSheet(index)" /></div><el-collapse v-model="expandedConfigSections" class="c31-page__execution-collapse c-series-no-collapse-motion"><el-collapse-item name="execution"><template #title><div class="c31-page__execution-collapse-title"><el-icon><Setting /></el-icon><div><strong>执行配置</strong><span>Token、认证方式和代理</span></div></div></template><ExecutionSettings v-if="executionSettingsMounted" v-model="draft.execution" :show-header="false" /></el-collapse-item></el-collapse></section>
      <section class="c31-page__section"><ParameterMatrixEditor v-model="draft.parameters" matrix /></section>
      <section class="c31-page__plan" :class="{ 'is-invalid': validationError }"><el-icon><WarningFilled /></el-icon><div><strong>{{ validationError || '批量计划已就绪' }}</strong><p v-if="!validationError">{{ parameterCount }} 个参数组合 × {{ titleGroups.size }} 个年份组，预计创建 {{ estimatedChildren }} 个 C3 子任务。</p></div></section>
      <footer class="c31-page__actions"><el-button :icon="RefreshRight" @click="clearDraft">清除草稿</el-button><div><el-button :icon="FolderChecked" @click="openSaveTemplate">保存模板</el-button><el-button type="primary" :icon="Promotion" :loading="submitting" :disabled="Boolean(validationError)" @click="submit">创建并执行</el-button></div></footer>
    </el-form>
    <el-dialog v-model="saveTemplateVisible" title="保存 C31 模板" width="420px"><el-form label-position="top"><el-form-item label="模板名称" required><el-input v-model="templateName" /></el-form-item><el-form-item label="模板描述"><el-input v-model="templateDescription" type="textarea" :rows="3" /></el-form-item></el-form><template #footer><el-button @click="saveTemplateVisible = false">取消</el-button><el-button type="primary" :loading="savingTemplate" @click="saveTemplate">保存</el-button></template></el-dialog>
    <C31BatchResultDialog v-if="batchResultVisible" v-model="batchResultVisible" :result="batchResult" @view-task="viewChildTask" @view-list="viewChildTasks" />
  </section>
</template>

<style scoped>
.c31-page { display: grid; gap: 16px; max-width: 1440px; margin: 0 auto; }.c31-page__header { display: flex; align-items: end; justify-content: space-between; gap: 16px; }.c31-page__header p { margin: 0 0 2px; color: var(--admin-text-muted); font-size: 13px; }.c31-page__header h1 { margin: 0; color: var(--admin-text); font-size: 20px; font-weight: 600; }.c31-page__form { display: grid; gap: 16px; }.c31-page__section { display: grid; gap: 16px; padding: 20px; border: 1px solid var(--admin-border); border-radius: var(--admin-radius); background: var(--admin-surface); }.c31-page__section-header { display: flex; align-items: start; justify-content: space-between; gap: 16px; }.c31-page__section h2 { margin: 0; color: var(--admin-text); font-size: 16px; font-weight: 600; }.c31-page__section p { margin: 4px 0 0; color: var(--admin-text-muted); font-size: 13px; }.c31-page__meta-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px 16px; }.c31-page__meta-grid :deep(.el-form-item) { margin-bottom: 0; }.c31-page__description { grid-column: span 2; }.c31-page__sheets { display: grid; gap: 12px; }.c31-page__execution-collapse { border-top: 1px solid var(--admin-border-light); border-bottom: 1px solid var(--admin-border-light); }.c31-page__execution-collapse :deep(.el-collapse-item__header) { height: 56px; border-bottom: 0; background: transparent; }.c31-page__execution-collapse :deep(.el-collapse-item__wrap) { border-bottom: 0; background: transparent; }.c31-page__execution-collapse :deep(.el-collapse-item__content) { padding-bottom: 16px; }.c31-page__execution-collapse-title { display: flex; align-items: center; gap: 10px; }.c31-page__execution-collapse-title > .el-icon { color: var(--admin-primary); font-size: 18px; }.c31-page__execution-collapse-title div { display: grid; gap: 1px; }.c31-page__execution-collapse-title strong { color: var(--admin-text); font-size: 14px; font-weight: 600; line-height: 20px; }.c31-page__execution-collapse-title span { color: var(--admin-text-muted); font-size: 12px; line-height: 18px; }.c31-page__plan { display: flex; gap: 12px; padding: 14px 16px; border: 1px solid var(--admin-success); border-radius: var(--admin-radius); background: rgb(16 185 129 / 8%); color: var(--admin-text-regular); }.c31-page__plan > .el-icon { flex: 0 0 auto; margin-top: 2px; color: var(--admin-success); font-size: 18px; }.c31-page__plan strong { font-size: 14px; }.c31-page__plan p { margin: 4px 0 0; color: var(--admin-text-muted); font-size: 13px; }.c31-page__plan.is-invalid { border-color: var(--admin-warning); background: rgb(245 158 11 / 9%); }.c31-page__plan.is-invalid > .el-icon { color: var(--admin-warning); }.c31-page__actions { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 16px 20px; border: 1px solid var(--admin-border); border-radius: var(--admin-radius); background: var(--admin-surface); }.c31-page__actions > div { display: flex; gap: 8px; }@media (max-width: 1100px) { .c31-page__meta-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }.c31-page__description { grid-column: span 2; } }@media (max-width: 640px) { .c31-page__header,.c31-page__actions { align-items: stretch; flex-direction: column; }.c31-page__section { padding: 16px; }.c31-page__section-header { flex-direction: column; }.c31-page__meta-grid { grid-template-columns: 1fr; }.c31-page__description { grid-column: auto; }.c31-page__actions > div { display: grid; grid-template-columns: 1fr 1fr; }.c31-page__actions > div :deep(.el-button) { margin: 0; } }
.c31-page__meta-grid :deep(.el-segmented) { width: 100%; }
</style>
