<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, reactive, shallowRef, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useStorage } from '@vueuse/core'
import dayjs from 'dayjs'
import { ArrowLeft, DocumentAdd, FolderChecked, Plus, Promotion, RefreshRight, Setting } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import TaskTemplateSelect from './TaskTemplateSelect.vue'
import GoogleSheetPicker from './GoogleSheetPicker.vue'
import ProductCodeEditor from './ProductCodeEditor.vue'
import DatePickerField from './DatePickerField.vue'
import { useDebouncedDraftStorage } from '../../composables/useDebouncedDraftStorage'
import { useTaskTemplates } from '../../composables/useTaskTemplates'
import { requestJson } from '../../api/http'
import { createEmptySheet, parseParameterInputs } from '../../utils/google-sheet-form'
import type { C57CreateDraft } from '../../types/google-sheet'
import type { TaskItem, TaskTemplate } from '../../types/api'

const loadExecutionSettings = () => import('./ExecutionSettings.vue')
const ExecutionSettings = defineAsyncComponent(loadExecutionSettings)

const props = defineProps<{
  taskType: 'google_sheet_C5' | 'google_sheet_C7'
  title: string
  listRoute: 'C5Tasks' | 'C7Tasks'
  detailRoute: 'C5TaskDetail' | 'C7TaskDetail'
}>()

const route = useRoute()
const router = useRouter()
const taskCode = computed(() => props.taskType.endsWith('C7') ? 'C7' : 'C5')
const defaultDraft = (): C57CreateDraft => {
  const endDate = dayjs().subtract(1, 'day')
  return {
    taskName: '', description: '', sheets: [createEmptySheet()],
    execution: { tokenType: 'file', tokenId: '', tokenFile: '', tokenJson: '', proxyUrl: '' },
    parameters: ['', '', ''], klineSource: 'auto', countMode: 'total', priceMode: 'vwap_price', marketType: 'cn', klineAdjustment: 'forward',
    dateRangeMode: [], excludeRecentYears: [], startDate: endDate.subtract(5, 'year').format('YYYY-MM-DD'), endDate: endDate.format('YYYY-MM-DD'),
  }
}
function cloneDraft(value: C57CreateDraft) { return JSON.parse(JSON.stringify(value)) as C57CreateDraft }

const storedDraft = useStorage<C57CreateDraft>(`google_sheet_${taskCode.value.toLowerCase()}_form_data`, defaultDraft())
const draft = reactive<C57CreateDraft>(cloneDraft(storedDraft.value))
const { templates, loading: loadingTemplates, loadTemplates: loadAvailableTemplates } = useTaskTemplates(props.taskType)
const templateOptions = computed(() => templates.value.map((template) => ({ label: template.name, value: template.id })))
const selectedTemplateId = shallowRef<number>()
const applyingTemplate = shallowRef(false)
const submitting = shallowRef(false)
const savingTemplate = shallowRef(false)
const saveTemplateVisible = shallowRef(false)
const templateName = shallowRef('')
const templateDescription = shallowRef('')
const expandedConfigSections = shallowRef<string[]>([])
const executionSettingsMounted = shallowRef(false)
let templateApplyVersion = 0

const parameterCount = computed(() => {
  try {
    const groups = parseParameterInputs(draft.parameters)
    return groups.length ? groups.reduce((total, group) => total * group.length, 1) : 0
  } catch {
    return 0
  }
})
const isCustomKline = computed(() => draft.klineSource === 'custom')

function normalizeSheets(value: unknown) {
  const source = Array.isArray(value) ? value : []
  const sheets = source.map((item) => {
    const sheet = item && typeof item === 'object' ? item as Record<string, unknown> : {}
    return { spreadsheetId: String(sheet.spreadsheet_id || sheet.spreadsheetId || ''), title: String(sheet.title || sheet.spreadsheet_title || ''), sheetName: String(sheet.sheet_name || sheet.sheetName || '') }
  }).filter((item) => item.spreadsheetId || item.title || item.sheetName)
  return sheets.length ? sheets : [createEmptySheet()]
}

function applyConfig(config: Record<string, unknown>, name = '', description = '') {
  const values = Array.isArray(config.parameters) ? config.parameters : []
  const nextDraft: C57CreateDraft = {
    taskName: name || String(config.base_task_name || ''),
    description: description || String(config.task_description || ''),
    sheets: normalizeSheets(config.sheets || [{ spreadsheet_id: config.spreadsheet_id, title: config.title || config.spreadsheet_title, sheet_name: config.sheet_name }]),
    execution: { tokenType: config.token_type === 'json' ? 'json' : 'file', tokenId: String(config.token_id || ''), tokenFile: String(config.token_file || ''), tokenJson: String(config.token_json || ''), proxyUrl: String(config.proxy_url || '') },
    parameters: Array.from({ length: 3 }, (_, index) => Array.isArray(values[index]) ? JSON.stringify(values[index]) : ''),
    klineSource: config.kline_source === 'custom' ? 'custom' : 'auto',
    countMode: config.count_mode === 'n_plus_1' ? 'n_plus_1' : 'total',
    priceMode: config.price_mode === 'kp_price' || config.price_mode === 'sp_price' ? config.price_mode : 'vwap_price',
    marketType: config.market_type === 'us' ? 'us' : 'cn',
    klineAdjustment: config.kline_adjustment === 'back' || config.kline_adjustment === 'none' ? config.kline_adjustment : 'forward',
    dateRangeMode: Array.isArray(config.date_range_mode) ? config.date_range_mode.filter((value): value is 'full' | 'recent' => value === 'full' || value === 'recent') : [],
    excludeRecentYears: Array.isArray(config.exclude_recent_years) ? config.exclude_recent_years.map(Number).filter((value) => Number.isInteger(value) && value >= 1 && value <= 10) : [],
    startDate: String(config.start_date || draft.startDate),
    endDate: String(config.end_date || draft.endDate),
  }
  Object.assign(draft, nextDraft)
}

async function loadTemplates(force = false) {
  try {
    await loadAvailableTemplates(force)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '加载模板失败')
  }
}

async function loadTemplate(templateId: number, applyVersion: number) {
  if (!templateId) return
  try {
    let cachedTemplate = templates.value.find((item) => item.id === templateId)
    if (!cachedTemplate) {
      await loadTemplates()
      cachedTemplate = templates.value.find((item) => item.id === templateId)
    }
    const template = cachedTemplate ?? await requestJson<TaskTemplate>(`/api/templates/${templateId}`)
    if (applyVersion !== templateApplyVersion || selectedTemplateId.value !== templateId) return
    applyConfig(template.config || {}, template.name, template.description || '')
    ElMessage.success('模板已应用')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '加载模板失败')
  }
}

function scheduleTemplateApply(templateId: number | undefined) {
  const applyVersion = ++templateApplyVersion
  applyingTemplate.value = Boolean(templateId)
  if (!templateId) return
  requestAnimationFrame(() => {
    window.setTimeout(() => {
      if (applyVersion !== templateApplyVersion || selectedTemplateId.value !== templateId) return
      void loadTemplate(templateId, applyVersion).finally(() => {
        if (applyVersion === templateApplyVersion) applyingTemplate.value = false
      })
    }, 0)
  })
}

async function loadRestart(taskId: string) {
  const applyVersion = ++templateApplyVersion
  applyingTemplate.value = true
  try {
    const payload = await requestJson<{ status: string; task: TaskItem }>(`/api/tasks/${encodeURIComponent(taskId)}`)
    if (applyVersion !== templateApplyVersion) return
    applyConfig(payload.task.config || {}, `${payload.task.name} (重启)`, payload.task.description || '')
    ElMessage.success('已加载原任务配置')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '加载重启配置失败')
  } finally {
    if (applyVersion === templateApplyVersion) applyingTemplate.value = false
  }
}

function buildConfig() {
  if (applyingTemplate.value) throw new Error('模板配置正在应用，请稍候')
  if (draft.sheets.some((sheet) => !sheet.spreadsheetId || !sheet.title)) throw new Error('请完善所有 Google Sheet 配置')
  const parameters = parseParameterInputs(draft.parameters)
  if (!parameters.length) throw new Error('请至少填写一组参数')
  if (draft.execution.tokenType === 'file' && !draft.execution.tokenId.trim()) throw new Error('请选择 Token')
  if (draft.execution.tokenType === 'json' && !draft.execution.tokenJson.trim()) throw new Error('请输入 Token JSON')
  const common = {
    token_type: draft.execution.tokenType,
    token_id: draft.execution.tokenType === 'file' ? draft.execution.tokenId || null : null,
    token_file: draft.execution.tokenFile || null,
    token_json: draft.execution.tokenType === 'json' ? draft.execution.tokenJson : null,
    proxy_url: draft.execution.proxyUrl || null,
    kline_source: draft.klineSource,
    parameters,
    sheets: draft.sheets.map((sheet) => ({ spreadsheet_id: sheet.spreadsheetId, title: sheet.title, sheet_name: sheet.sheetName || undefined })),
  }
  if (isCustomKline.value) {
    return { ...common, count_mode: 'total', market_type: 'custom', price_mode: null, kline_adjustment: null, date_range_mode: [], exclude_recent_years: [], start_date: null, end_date: null }
  }
  return { ...common, count_mode: draft.countMode, price_mode: draft.priceMode, market_type: draft.marketType, kline_adjustment: draft.klineAdjustment, date_range_mode: draft.countMode === 'n_plus_1' ? draft.dateRangeMode : [], exclude_recent_years: draft.excludeRecentYears, start_date: draft.startDate || null, end_date: draft.endDate || null }
}

function addSheet() { draft.sheets.push(createEmptySheet()) }
function removeSheet(index: number) { if (draft.sheets.length > 1) draft.sheets.splice(index, 1) }

async function submit() {
  try {
    const config = buildConfig()
    submitting.value = true
    const response = await requestJson<{ status: string; task_id: string; message?: string }>('/api/tasks', { method: 'POST', body: JSON.stringify({ name: draft.taskName.trim() || `Google Sheet ${taskCode.value} - ${dayjs().format('YYYY-MM-DD HH:mm:ss')}`, description: draft.description.trim() || `批量执行 ${parameterCount.value} 个参数组合`, task_type: props.taskType, config }) })
    Object.assign(draft, defaultDraft())
    storedDraft.value = defaultDraft()
    ElMessage.success(response.message || `${taskCode.value} 任务已创建并启动`)
    void router.push({ name: props.detailRoute, params: { taskId: response.task_id } })
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '创建任务失败')
  } finally {
    submitting.value = false
  }
}

async function clearDraft() {
  await ElMessageBox.confirm('确定清除当前草稿吗？', '清除草稿', { type: 'warning', confirmButtonText: '清除' })
  templateApplyVersion += 1
  applyingTemplate.value = false
  Object.assign(draft, defaultDraft())
  storedDraft.value = defaultDraft()
  selectedTemplateId.value = undefined
}

function returnToTaskList() { void router.push({ name: props.listRoute }) }
function openSaveTemplate() { templateName.value = draft.taskName ? `${draft.taskName} 模板` : ''; templateDescription.value = draft.description; saveTemplateVisible.value = true }
async function saveTemplate() {
  try {
    if (!templateName.value.trim()) throw new Error('请输入模板名称')
    savingTemplate.value = true
    await requestJson('/api/templates', { method: 'POST', body: JSON.stringify({ name: templateName.value.trim(), description: templateDescription.value.trim(), config: { ...buildConfig(), task_type: props.taskType } }) })
    saveTemplateVisible.value = false
    ElMessage.success('模板已保存')
    void loadTemplates(true)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '保存模板失败')
  } finally {
    savingTemplate.value = false
  }
}

watch(() => draft.klineSource, (value) => { if (value === 'custom') { draft.countMode = 'total'; draft.dateRangeMode = []; draft.excludeRecentYears = [] } })
watch(() => draft.countMode, (value) => { if (value !== 'n_plus_1') draft.dateRangeMode = [] })
watch(expandedConfigSections, (sections) => { if (sections.includes('execution')) executionSettingsMounted.value = true })
useDebouncedDraftStorage(draft, storedDraft, cloneDraft)

onMounted(() => {
  const prefetch = () => { void loadExecutionSettings() }
  if (typeof window.requestIdleCallback === 'function') window.requestIdleCallback(prefetch, { timeout: 1200 })
  else window.setTimeout(prefetch, 300)
})

void loadTemplates()
const templateId = Number(route.query.template_id)
const restartTaskId = typeof route.query.restart_task_id === 'string' ? route.query.restart_task_id : ''
if (templateId) { selectedTemplateId.value = templateId; scheduleTemplateApply(templateId) } else if (restartTaskId) void loadRestart(restartTaskId)
</script>

<template>
  <section class="c57-create-page">
    <header class="c57-create-page__header">
      <div><p>业务模块 / Google Sheet</p><h1>{{ title }}</h1></div>
      <el-button :icon="ArrowLeft" @click="returnToTaskList">返回任务列表</el-button>
    </header>
    <el-form class="c57-create-page__form" label-position="top" @submit.prevent>
      <section class="c57-create-page__section">
        <header class="c57-create-page__section-header">
          <div><h2>任务信息</h2><p>选择模板或填写任务说明，名称留空时自动生成。</p></div>
        </header>
        <div class="c57-create-page__meta-grid">
          <el-form-item label="任务模板">
            <TaskTemplateSelect v-model="selectedTemplateId" :options="templateOptions" :loading="loadingTemplates" @change="scheduleTemplateApply" />
          </el-form-item>
          <el-form-item label="任务名称"><el-input v-model="draft.taskName" placeholder="留空自动生成" /></el-form-item>
          <el-form-item class="c57-create-page__description" label="任务描述"><el-input v-model="draft.description" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }" placeholder="可选，记录任务用途" /></el-form-item>
        </div>
      </section>

      <section class="c57-create-page__section">
        <header class="c57-create-page__section-header">
          <div><h2>Google Sheet 配置</h2><p>工作表可选；留空时按表标题的默认输出结构执行。</p></div>
          <el-button :icon="Plus" @click="addSheet">添加 Sheet</el-button>
        </header>
        <div class="c57-create-page__sheets">
          <GoogleSheetPicker
            v-for="(_, index) in draft.sheets"
            :key="index"
            v-model="draft.sheets[index]"
            :index="index"
            :removable="draft.sheets.length > 1"
            :proxy-url="draft.execution.proxyUrl"
            :table-type="taskCode.toLowerCase()"
            :worksheet-required="false"
            @remove="removeSheet(index)"
          />
        </div>
        <el-collapse v-model="expandedConfigSections" class="c57-create-page__execution-collapse c-series-no-collapse-motion">
          <el-collapse-item name="execution">
            <template #title><div class="c57-create-page__execution-title"><el-icon><Setting /></el-icon><div><strong>执行配置</strong><span>Token、认证方式和代理</span></div></div></template>
            <ExecutionSettings v-if="executionSettingsMounted" v-model="draft.execution" :show-header="false" />
          </el-collapse-item>
        </el-collapse>
      </section>

      <section class="c57-create-page__section">
        <header class="c57-create-page__section-header">
          <div><h2>K 线与参数</h2><p>先填写参数矩阵，再配置数据来源和行情规则。</p></div>
        </header>
        <section class="c57-create-page__semantic-group c57-create-page__semantic-group--parameters">
          <header class="c57-create-page__group-header">
            <h3>参数矩阵</h3>
            <p>股票代码占满一行；参数 2、参数 3 等宽排列。</p>
          </header>
          <ProductCodeEditor v-model="draft.parameters[0]" />
          <div class="c57-create-page__parameter-json-grid">
            <el-form-item v-for="(_, index) in draft.parameters.slice(1)" :key="index" :label="`参数 ${index + 2} JSON（可选）`">
              <el-input v-model="draft.parameters[index + 1]" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" placeholder='例如：[1, 2, 3]' />
            </el-form-item>
          </div>
        </section>

        <section class="c57-create-page__semantic-group">
          <header class="c57-create-page__group-header">
            <h3>数据来源与计算口径</h3>
            <p>先确定 K 线来源，再显示对应的计算选项。</p>
          </header>
          <div class="c57-create-page__source-grid" :class="{ 'c57-create-page__source-grid--custom': isCustomKline }">
            <el-form-item label="K 线来源"><el-segmented v-model="draft.klineSource" :options="[{ label: '自动获取', value: 'auto' }, { label: 'Sheet 自定义', value: 'custom' }]" /></el-form-item>
            <template v-if="!isCustomKline">
              <el-form-item label="统计方式"><el-segmented v-model="draft.countMode" :options="[{ label: '总数', value: 'total' }, { label: 'N+1', value: 'n_plus_1' }]" /></el-form-item>
              <el-form-item label="价格类型"><el-segmented v-model="draft.priceMode" :options="[{ label: 'VWAP', value: 'vwap_price' }, { label: '开盘价', value: 'kp_price' }, { label: '收盘价', value: 'sp_price' }]" /></el-form-item>
              <el-form-item label="市场类型"><el-segmented v-model="draft.marketType" :options="[{ label: 'A 股', value: 'cn' }, { label: '美股', value: 'us' }]" /></el-form-item>
            </template>
          </div>
          <el-alert v-if="isCustomKline" title="自定义 K 线模式会固定为总数统计，并禁用自动行情、复权与日期范围设置。" type="info" :closable="false" show-icon />
        </section>

        <section v-if="!isCustomKline" class="c57-create-page__semantic-group">
          <header class="c57-create-page__group-header">
            <h3>行情规则与日期范围</h3>
            <p>复权和日期共同决定任务读取的行情区间。</p>
          </header>
          <div class="c57-create-page__rule-grid">
            <el-form-item label="K 线复权"><el-segmented v-model="draft.klineAdjustment" :options="[{ label: '前复权', value: 'forward' }, { label: '后复权', value: 'back' }, { label: '不复权', value: 'none' }]" /></el-form-item>
            <el-form-item label="范围模式"><el-checkbox-group v-model="draft.dateRangeMode" :disabled="draft.countMode !== 'n_plus_1'"><el-checkbox value="full">整年</el-checkbox><el-checkbox value="recent">近年</el-checkbox></el-checkbox-group></el-form-item>
            <el-form-item label="排除近年">
              <el-checkbox-group v-model="draft.excludeRecentYears" class="c57-create-page__exclude-years">
                <el-checkbox v-for="year in 10" :key="year" :value="year">{{ year }} 年</el-checkbox>
              </el-checkbox-group>
            </el-form-item>
            <el-form-item label="日期范围">
              <div class="c57-create-page__date-range">
                <DatePickerField v-model="draft.startDate" type="date" value-format="YYYY-MM-DD" placeholder="开始日期" />
                <span>至</span>
                <DatePickerField v-model="draft.endDate" type="date" value-format="YYYY-MM-DD" placeholder="结束日期" />
              </div>
            </el-form-item>
          </div>
        </section>

      </section>

      <footer class="c57-create-page__actions">
        <el-tag type="info" effect="plain">预计 {{ parameterCount }} 个参数组合 × {{ draft.sheets.length }} 个 Sheet</el-tag>
        <div>
          <el-button :icon="RefreshRight" @click="clearDraft">清除草稿</el-button>
          <el-button :icon="FolderChecked" :disabled="applyingTemplate" @click="openSaveTemplate">保存模板</el-button>
          <el-button type="primary" :icon="Promotion" :loading="submitting" :disabled="applyingTemplate" @click="submit">创建并执行</el-button>
        </div>
      </footer>
    </el-form>
    <el-dialog v-model="saveTemplateVisible" :title="`保存 ${taskCode} 模板`" width="420px">
      <el-form label-position="top"><el-form-item label="模板名称" required><el-input v-model="templateName" /></el-form-item><el-form-item label="模板描述"><el-input v-model="templateDescription" type="textarea" :rows="3" /></el-form-item></el-form>
      <template #footer><el-button @click="saveTemplateVisible = false">取消</el-button><el-button type="primary" :icon="DocumentAdd" :loading="savingTemplate" @click="saveTemplate">保存</el-button></template>
    </el-dialog>
  </section>
</template>

<style scoped>
.c57-create-page {
  display: grid;
  max-width: 1440px;
  gap: 16px;
  margin: 0 auto;
}

.c57-create-page__header,
.c57-create-page__actions {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 16px;
}

.c57-create-page__header p {
  margin: 0 0 2px;
  color: var(--admin-text-muted);
  font-size: 13px;
}

.c57-create-page__header h1 {
  margin: 0;
  color: var(--admin-text);
  font-size: 20px;
  font-weight: 600;
  line-height: 28px;
}

.c57-create-page__form,
.c57-create-page__sheets {
  display: grid;
  gap: 16px;
}

.c57-create-page__section {
  display: grid;
  min-width: 0;
  gap: 16px;
  padding: 20px;
  border: 1px solid var(--admin-border);
  border-radius: var(--admin-radius);
  background: var(--admin-surface);
}

.c57-create-page__section-header {
  display: flex;
  align-items: start;
  justify-content: space-between;
  gap: 16px;
}

.c57-create-page__section-header h2 {
  margin: 0;
  color: var(--admin-text);
  font-size: 16px;
  font-weight: 600;
  line-height: 24px;
}

.c57-create-page__section-header p {
  margin: 4px 0 0;
  color: var(--admin-text-muted);
  font-size: 13px;
  line-height: 20px;
}

.c57-create-page__meta-grid {
  display: grid;
  grid-template-columns: minmax(180px, 0.8fr) minmax(220px, 1fr) minmax(260px, 1.3fr);
  gap: 16px;
}

.c57-create-page__semantic-group {
  min-width: 0;
}

.c57-create-page__semantic-group + .c57-create-page__semantic-group {
  padding-top: 18px;
  border-top: 1px solid var(--admin-border-light);
}

.c57-create-page__group-header {
  margin-bottom: 14px;
}

.c57-create-page__group-header h3,
.c57-create-page__group-header p {
  margin: 0;
}

.c57-create-page__group-header h3 {
  color: var(--admin-text);
  font-size: 14px;
  font-weight: 600;
  line-height: 22px;
}

.c57-create-page__group-header p {
  margin-top: 2px;
  color: var(--admin-text-muted);
  font-size: 12px;
  line-height: 20px;
}

.c57-create-page__source-grid,
.c57-create-page__rule-grid,
.c57-create-page__parameter-json-grid {
  display: grid;
  gap: 16px;
}

.c57-create-page__source-grid {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.c57-create-page__source-grid--custom {
  grid-template-columns: minmax(280px, 460px);
}

.c57-create-page__rule-grid {
  grid-template-columns: minmax(170px, 0.8fr) minmax(220px, 1fr) minmax(180px, 0.9fr) minmax(420px, 1.7fr);
}

.c57-create-page__parameter-json-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  margin-top: 16px;
}

.c57-create-page__date-range {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  align-items: center;
  gap: 8px;
  width: 100%;
  color: var(--admin-text-muted);
  font-size: 13px;
}

.c57-create-page__semantic-group > :deep(.el-alert) {
  margin-top: 14px;
}

.c57-create-page :deep(.el-form-item) {
  margin-bottom: 0;
}

.c57-create-page__source-grid :deep(.el-segmented),
.c57-create-page__rule-grid :deep(.el-segmented),
.c57-create-page__date-range :deep(.el-date-editor) {
  width: 100%;
}

.c57-create-page__exclude-years {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 12px;
}

.c57-create-page__exclude-years :deep(.el-checkbox) {
  margin-right: 0;
}

.c57-create-page__execution-collapse {
  border-top: 1px solid var(--admin-border-light);
  border-bottom: 1px solid var(--admin-border-light);
}

.c57-create-page__execution-collapse :deep(.el-collapse-item__header),
.c57-create-page__execution-collapse :deep(.el-collapse-item__wrap) {
  border-bottom: 0;
  background: transparent;
}

.c57-create-page__execution-collapse :deep(.el-collapse-item__header) {
  height: 56px;
}

.c57-create-page__execution-collapse :deep(.el-collapse-item__content) {
  padding-bottom: 16px;
}

.c57-create-page__execution-title {
  display: flex;
  align-items: center;
  gap: 10px;
}

.c57-create-page__execution-title > .el-icon {
  color: var(--admin-primary);
  font-size: 18px;
}

.c57-create-page__execution-title div {
  display: grid;
  gap: 1px;
}

.c57-create-page__execution-title strong {
  color: var(--admin-text);
  font-size: 14px;
  font-weight: 600;
  line-height: 20px;
}

.c57-create-page__execution-title span {
  color: var(--admin-text-muted);
  font-size: 12px;
  line-height: 18px;
}

.c57-create-page__actions {
  position: sticky;
  bottom: 0;
  z-index: 3;
  align-items: center;
  padding: 16px 20px;
  border: 1px solid var(--admin-border);
  border-radius: var(--admin-radius);
  background: var(--admin-surface);
  box-shadow: 0 -4px 12px rgb(15 23 42 / 4%);
}

.c57-create-page__actions > div {
  display: flex;
  flex-wrap: wrap;
  justify-content: end;
  gap: 8px;
}

@media (max-width: 1180px) {
  .c57-create-page__source-grid,
  .c57-create-page__rule-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .c57-create-page__source-grid--custom {
    grid-template-columns: minmax(280px, 460px);
  }

  .c57-create-page__rule-grid :deep(.el-form-item:last-child) {
    grid-column: 1 / -1;
  }
}

@media (max-width: 900px) {
  .c57-create-page__meta-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .c57-create-page__description {
    grid-column: 1 / -1;
  }
}

@media (max-width: 640px) {
  .c57-create-page__header,
  .c57-create-page__actions {
    align-items: stretch;
    flex-direction: column;
  }

  .c57-create-page__meta-grid,
  .c57-create-page__source-grid,
  .c57-create-page__source-grid--custom,
  .c57-create-page__rule-grid,
  .c57-create-page__parameter-json-grid {
    grid-template-columns: 1fr;
  }

  .c57-create-page__section {
    padding: 16px;
  }

  .c57-create-page__section-header {
    flex-direction: column;
  }

  .c57-create-page__description,
  .c57-create-page__rule-grid :deep(.el-form-item:last-child) {
    grid-column: auto;
  }

  .c57-create-page__date-range {
    grid-template-columns: 1fr;
  }

  .c57-create-page__date-range > span {
    display: none;
  }

  .c57-create-page__actions {
    position: static;
    padding: 16px;
  }

  .c57-create-page__actions > div {
    display: grid;
    grid-template-columns: 1fr 1fr;
  }

  .c57-create-page__actions > div :deep(.el-button:last-child) {
    grid-column: 1 / -1;
  }
}
</style>
