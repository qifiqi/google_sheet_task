<template>
  <div class="app-page task-create-batch">
    <div class="page-toolbar">
      <div class="page-toolbar__meta">
        <div class="page-toolbar__eyebrow">Batch Builder</div>
        <h2 class="page-title">{{ pageTitle }}</h2>
        <p class="page-description">按股票代码、参数组合和多组 Sheet 配置批量创建子任务，适合批量回放与拆分执行。</p>
      </div>
      <div class="page-toolbar__actions">
        <el-button class="page-back-button" @click="$router.back()">返回</el-button>
      </div>
    </div>

    <el-card shadow="never" class="page-section">
      <div class="section-heading">
        <h3 class="section-title section-title--muted">任务基本信息</h3>
      </div>
      <el-row :gutter="16">
        <el-col :xs="24" :sm="6">
          <el-form-item label="选择模板">
            <el-select v-model="selectedTemplate" placeholder="不使用模板" clearable class="full-width" @change="applyTemplate">
              <el-option v-for="t in templates" :key="t.id" :value="t.id" :label="t.name" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :xs="24" :sm="6">
          <el-form-item label="任务 Base Name">
            <el-input v-model="form.base_task_name" placeholder="如 strategy_batch，子任务自动追加序号" />
          </el-form-item>
        </el-col>
        <el-col :xs="24" :sm="6">
          <el-form-item label="任务描述">
            <el-input v-model="form.description" type="textarea" :rows="1" placeholder="用于批量任务备注" />
          </el-form-item>
        </el-col>
        <el-col :xs="24" :sm="6">
          <el-form-item label="股票代码">
            <div class="control-row control-row--stretch">
              <el-input v-model="stockCodeInput" placeholder="如 601727,600000" @keyup.enter="addStockCodes" />
              <el-button @click="addStockCodes">添加</el-button>
            </div>
          </el-form-item>
        </el-col>
        <el-col :xs="24" :sm="3">
          <el-form-item label="结束日期">
            <el-date-picker v-model="form.end_date" type="date" value-format="YYYY-MM-DD" class="full-width" placeholder="按后端默认值" />
          </el-form-item>
        </el-col>
        <el-col :xs="24" :sm="3">
          <el-form-item label="市场类型">
            <el-radio-group v-model="form.market_type">
              <el-radio-button value="cn">A股</el-radio-button>
              <el-radio-button value="en">美股</el-radio-button>
            </el-radio-group>
          </el-form-item>
        </el-col>
        <el-col :xs="24" :sm="3">
          <el-form-item label="K线复权">
            <el-select v-model="form.kline_adjustment" class="full-width">
              <el-option value="forward" label="前复权" />
              <el-option value="back" label="后复权" />
              <el-option value="none" label="不复权" />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>
      <div class="tag-wall">
        <el-tag v-for="code in stockCodes" :key="code" closable @close="removeStockCode(code)">{{ code }}</el-tag>
        <span v-if="!stockCodes.length" class="panel-note">暂无股票代码</span>
      </div>
    </el-card>

    <el-card shadow="never" class="page-section">
      <div class="section-heading">
        <h3 class="section-title section-title--muted">Google Sheet 配置</h3>
      </div>

      <div v-for="(sheet, idx) in sheetConfigs" :key="idx" class="sub-card task-create-batch__sheet-card">
        <div class="section-heading task-create-batch__sheet-head">
          <span class="task-create-batch__sheet-title">表格配置 {{ idx + 1 }}</span>
          <el-button v-if="idx > 0" link type="danger" size="small" @click="removeSheet(idx)">移除</el-button>
        </div>
        <el-row :gutter="12">
          <el-col :xs="24" :sm="10">
            <el-form-item label="选择 Google Sheet">
              <div class="control-row control-row--stretch">
                <el-select v-model="sheet.spreadsheet_id" placeholder="请选择" filterable class="full-width" @change="loadWorksheetsForSheet(idx)">
                  <el-option v-for="s in sheets" :key="s.spreadsheet_id" :value="s.spreadsheet_id" :label="`${s.name} (${s.spreadsheet_id})`" />
                </el-select>
                <el-button :loading="sheetListLoading" @click="refreshSheets">刷新</el-button>
              </div>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="7">
            <el-form-item label="表标题">
              <el-input v-model="sheet.title" placeholder="格式：前缀-1y-3]" />
              <div class="panel-note task-create-batch__field-note">必须以 -数字y-数字] 结尾</div>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="7">
            <el-form-item label="工作表名称">
              <el-input v-model="sheet.sheet_name" placeholder="选择后自动带出" />
            </el-form-item>
          </el-col>
        </el-row>
      </div>

      <div class="section-actions task-create-batch__sheet-actions">
        <el-button size="small" @click="addSheet">添加一组表格配置</el-button>
        <el-button size="small" type="danger" plain @click="removeSheet(sheetConfigs.length - 1)" :disabled="sheetConfigs.length <= 1">
          移除最后一组
        </el-button>
      </div>

      <el-collapse v-model="advancedOpen" class="task-create-batch__collapse">
        <el-collapse-item title="更多配置" name="advanced">
          <el-row :gutter="16">
            <el-col :xs="24" :sm="6">
              <el-form-item label="认证方式">
                <el-select v-model="form.token_type" class="full-width">
                  <el-option value="file" label="Token 文件路径" />
                  <el-option value="json" label="Token JSON 字符串" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col v-if="form.token_type === 'file'" :xs="24" :sm="18">
              <el-form-item label="Token 选择">
                <el-select v-model="form.token_id" class="full-width task-create-batch__field-gap" placeholder="选择 Token">
                  <el-option :value="RANDOM_TOKEN" label="随机 Token（系统自动选择未达上限的 Token）" />
                  <el-option
                    v-for="t in tokens"
                    :key="t.id"
                    :value="String(t.id)"
                    :label="`${t.name} | 占用 ${t.current_in_use_count || 0} | 累计 ${t.task_usage_count} | 上限 ${t.max_usage_count > 0 ? t.max_usage_count : '无限'}`"
                    :disabled="!t.is_available"
                  />
                </el-select>
                <div class="control-row control-row--stretch">
                  <el-input v-model="tokenImportPath" placeholder="输入 Token 文件路径后点击导入" />
                  <el-button @click="doImportToken">导入</el-button>
                </div>
              </el-form-item>
            </el-col>
            <el-col v-else :xs="24" :sm="18">
              <el-form-item label="Token JSON">
                <el-input v-model="form.token_json" type="textarea" :rows="3" placeholder='{"installed": {...}}' />
              </el-form-item>
            </el-col>
            <el-col :xs="24" :sm="12">
              <el-form-item label="代理 URL">
                <el-input v-model="form.proxy_url" placeholder="可选" />
              </el-form-item>
            </el-col>
          </el-row>
        </el-collapse-item>
      </el-collapse>
    </el-card>

    <el-card shadow="never" class="page-section">
      <div class="section-heading">
        <h3 class="section-title section-title--muted">参数配置</h3>
      </div>
      <div class="panel-note task-create-batch__intro">每个参数支持一维或二维数组，如 `[1,2,3]` 或 `[[1,"A"],[2,"B"]]`。</div>
      <el-row :gutter="12">
        <el-col v-for="(p, i) in params" :key="i" :xs="24" :sm="12" class="task-create-batch__param-col">
          <el-card shadow="never" class="task-create-batch__param-card" :style="{ borderColor: paramColors[i] }">
            <div class="task-create-batch__param-title">参数 {{ i + 1 }}</div>
            <el-input v-model="params[i]" type="textarea" :rows="3" :placeholder='`["A","B"] 或 [[1,"A"],[2,"B"]]`' />
          </el-card>
        </el-col>
      </el-row>
    </el-card>

    <el-card v-if="combinationCount > 0" shadow="never" class="page-section">
      <div class="info-banner task-create-batch__summary">
        <span>
          <el-tag type="primary">{{ stockCodes.length }}</el-tag> 个股票
          <el-tag type="success">{{ singleCombinationCount }}</el-tag> 个参数组合
          <el-tag type="warning">{{ sheetConfigs.filter((s) => s.spreadsheet_id).length }}</el-tag> 组表格
          = <el-tag>{{ combinationCount }}</el-tag> 个子任务
        </span>
      </div>
    </el-card>

    <el-card shadow="never">
      <div class="action-bar">
        <el-button @click="clearSaved">清除数据</el-button>
        <el-button @click="saveTemplateVisible = true">保存为模板</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">创建任务并执行</el-button>
      </div>
    </el-card>

    <el-dialog v-model="saveTemplateVisible" title="保存为模板" width="480px" :fullscreen="isMobile">
      <el-form label-width="80px">
        <el-form-item label="模板名称"><el-input v-model="templateForm.name" /></el-form-item>
        <el-form-item label="模板描述"><el-input v-model="templateForm.description" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="saveTemplateVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingTemplate" @click="doSaveTemplate">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getGoogleSheets, getWorksheets, getTokens, importToken as apiImportToken } from '@/api/googleSheet'
import { batchCreateTasks, getTask } from '@/api/task'
import { getTemplates, getTemplate, createTemplate } from '@/api/template'
import { useResponsive } from '@/composables/useResponsive'

const route = useRoute()
const router = useRouter()
const { isMobile } = useResponsive()

const RANDOM_TOKEN = '__random__'
const LS_KEY = 'google_sheet_c31_form_data'
const paramColors = ['#409eff', '#67c23a', '#17a2b8', '#e6a23c', '#f56c6c', '#909399']

const pageTitle = ref('创建批量任务 (C31)')
const sheets = ref([])
const tokens = ref([])
const templates = ref([])
const selectedTemplate = ref('')
const advancedOpen = ref([])
const sheetListLoading = ref(false)
const submitting = ref(false)
const saveTemplateVisible = ref(false)
const savingTemplate = ref(false)
const tokenImportPath = ref('')
const stockCodeInput = ref('')
const stockCodes = ref([])

const form = reactive({
  base_task_name: '', description: '', end_date: '', market_type: 'cn', kline_adjustment: 'forward',
  token_type: 'file', token_id: RANDOM_TOKEN, token_json: '', proxy_url: ''
})

const sheetConfigs = ref([{ spreadsheet_id: '', title: '', sheet_name: '' }])
const params = ref(['', '', '', '', '', ''])
const templateForm = reactive({ name: '', description: '' })

function parseJsonArray(str) {
  if (!str || !str.trim()) return null
  try { const v = JSON.parse(str); return Array.isArray(v) ? v : null } catch { return null }
}

const singleCombinationCount = computed(() => {
  const arrays = params.value.map((p) => parseJsonArray(p)).filter((a) => a && a.length > 0)
  if (!arrays.length) return 0
  return arrays.reduce((acc, a) => acc * a.length, 1)
})

const combinationCount = computed(() => {
  const validSheets = sheetConfigs.value.filter((s) => s.spreadsheet_id).length
  return stockCodes.value.length * singleCombinationCount.value * validSheets
})

function addStockCodes() {
  const parts = stockCodeInput.value.split(/[,\s]+/).map((p) => p.trim()).filter((p) => p)
  if (!parts.length) return
  const set = new Set(stockCodes.value)
  parts.forEach((code) => set.add(code))
  stockCodes.value = Array.from(set)
  stockCodeInput.value = ''
}

function removeStockCode(code) {
  stockCodes.value = stockCodes.value.filter((c) => c !== code)
}

function addSheet() {
  sheetConfigs.value.push({ spreadsheet_id: '', title: '', sheet_name: '' })
}

function removeSheet(idx) {
  if (sheetConfigs.value.length <= 1) {
    ElMessage.info('至少保留一组表格配置')
    return
  }
  sheetConfigs.value.splice(idx, 1)
}

async function loadSheets() {
  sheetListLoading.value = true
  try {
    const res = await getGoogleSheets({ only_available: 1, table_type: 'c3' })
    sheets.value = res.items || []
  } finally {
    sheetListLoading.value = false
  }
}

async function loadTokens() {
  try {
    const res = await getTokens()
    tokens.value = res.tokens || []
  } catch {}
}

async function loadTemplates() {
  try {
    const res = await getTemplates({ task_type: 'google_sheet_C31' })
    templates.value = res.templates || []
  } catch {}
}

function ensureSheetOption(spreadsheetId, title = '') {
  if (!spreadsheetId) return
  if (sheets.value.some((sheet) => sheet.spreadsheet_id === spreadsheetId)) return
  sheets.value = [
    ...sheets.value,
    {
      spreadsheet_id: spreadsheetId,
      name: title || `历史配置 ${spreadsheetId.slice(0, 8)}`
    }
  ]
}

async function refreshSheets() {
  await loadSheets()
  sheetConfigs.value.forEach((sheet) => ensureSheetOption(sheet.spreadsheet_id, sheet.title))
  ElMessage.success('Google Sheet 列表已刷新')
}

async function loadWorksheetsForSheet(idx) {
  const sheet = sheetConfigs.value[idx]
  if (!sheet.spreadsheet_id) return
  try {
    const res = await getWorksheets({ spreadsheet_id: sheet.spreadsheet_id, token_id: form.token_id, proxy_url: form.proxy_url || undefined })
    if (res.title) sheet.title = res.title
    if (res.worksheets?.length) sheet.sheet_name = res.worksheets[0]
    ElMessage.success('工作表已加载')
  } catch {
    ElMessage.error('获取工作表失败')
  }
}

async function applyTemplate(id) {
  if (!id) return
  try {
    const tpl = await getTemplate(id)
    const config = typeof tpl.config === 'string' ? JSON.parse(tpl.config) : (tpl.config || {})
    form.base_task_name = config.base_task_name || ''
    form.description = config.task_description || tpl.description || ''
    form.end_date = config.end_date || ''
    form.market_type = config.market_type || 'cn'
    form.kline_adjustment = config.kline_adjustment || 'forward'
    form.token_type = config.token_type || 'file'
    form.token_id = config.token_id ? String(config.token_id) : RANDOM_TOKEN
    form.token_json = config.token_json || ''
    form.proxy_url = config.proxy_url || ''
    stockCodes.value = Array.isArray(config.stock_codes) ? [...config.stock_codes] : []
    if (Array.isArray(config.sheets) && config.sheets.length) {
      sheetConfigs.value = config.sheets.map((sheet) => {
        ensureSheetOption(sheet.spreadsheet_id, sheet.title)
        return {
          spreadsheet_id: sheet.spreadsheet_id || '',
          title: sheet.title || '',
          sheet_name: sheet.sheet_name || ''
        }
      })
    }
    if (Array.isArray(config.parameters)) {
      params.value = config.parameters.map((param) => Array.isArray(param) ? JSON.stringify(param) : '')
      while (params.value.length < 6) params.value.push('')
    }
    ElMessage.success('已加载模板配置')
  } catch {
    ElMessage.error('加载模板失败')
  }
}

async function loadRestartTask(taskId) {
  try {
    const res = await getTask(taskId)
    const task = res.task || res
    const config = task.config || {}
    pageTitle.value = '重启批量任务 (C31)'
    form.base_task_name = config.base_task_name || task.name || ''
    form.description = config.task_description || task.description || ''
    form.end_date = config.end_date || ''
    form.market_type = config.market_type || 'cn'
    form.kline_adjustment = config.kline_adjustment || 'forward'
    form.token_type = config.token_type || 'file'
    form.token_id = config.token_id ? String(config.token_id) : RANDOM_TOKEN
    form.token_json = config.token_json || ''
    form.proxy_url = config.proxy_url || ''
    stockCodes.value = Array.isArray(config.stock_codes) ? [...config.stock_codes] : []
    if (Array.isArray(config.sheets) && config.sheets.length) {
      sheetConfigs.value = config.sheets.map((sheet) => {
        ensureSheetOption(sheet.spreadsheet_id, sheet.title)
        return {
          spreadsheet_id: sheet.spreadsheet_id || '',
          title: sheet.title || '',
          sheet_name: sheet.sheet_name || ''
        }
      })
    }
    if (Array.isArray(config.parameters)) {
      params.value = config.parameters.map((param) => Array.isArray(param) ? JSON.stringify(param) : '')
      while (params.value.length < 6) params.value.push('')
    }
    ElMessage.info('已加载原任务配置')
  } catch {
    ElMessage.error('加载原任务失败')
  }
}

async function doImportToken() {
  if (!tokenImportPath.value.trim()) {
    ElMessage.warning('请输入 Token 文件路径')
    return
  }
  try {
    const res = await apiImportToken({ token_file: tokenImportPath.value.trim() })
    ElMessage.success(res.message || 'Token 导入成功')
    tokenImportPath.value = ''
    await loadTokens()
    if (res.token?.id) form.token_id = String(res.token.id)
  } catch {
    ElMessage.error('导入 Token 失败')
  }
}

function saveFormData() {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify({ ...form, sheetConfigs: sheetConfigs.value, stockCodes: stockCodes.value, params: params.value }))
  } catch {}
}

function loadSavedFormData() {
  try {
    const saved = localStorage.getItem(LS_KEY)
    if (!saved) return
    const data = JSON.parse(saved)
    Object.assign(form, {
      base_task_name: data.base_task_name || '',
      description: data.description || '',
      end_date: data.end_date || '',
      market_type: data.market_type || 'cn',
      kline_adjustment: data.kline_adjustment || 'forward',
      token_type: data.token_type || 'file',
      token_id: data.token_id || RANDOM_TOKEN,
      token_json: data.token_json || '',
      proxy_url: data.proxy_url || ''
    })
    if (Array.isArray(data.sheetConfigs)) {
      sheetConfigs.value = data.sheetConfigs
      sheetConfigs.value.forEach((sheet) => ensureSheetOption(sheet.spreadsheet_id, sheet.title))
    }
    if (Array.isArray(data.stockCodes)) stockCodes.value = data.stockCodes
    if (Array.isArray(data.params)) params.value = data.params
    ElMessage.info('表单数据已恢复')
  } catch {}
}

function clearSaved() {
  localStorage.removeItem(LS_KEY)
  Object.assign(form, { base_task_name: '', description: '', end_date: '', market_type: 'cn', kline_adjustment: 'forward', token_type: 'file', token_id: RANDOM_TOKEN, token_json: '', proxy_url: '' })
  sheetConfigs.value = [{ spreadsheet_id: '', title: '', sheet_name: '' }]
  stockCodes.value = []
  params.value = ['', '', '', '', '', '']
  ElMessage.success('已清除保存的表单数据')
}

async function submit() {
  if (!form.base_task_name.trim()) { ElMessage.error('请输入任务 Base Name'); return }
  if (!stockCodes.value.length) { ElMessage.error('请至少输入一个股票代码'); return }
  const validSheets = sheetConfigs.value.filter((s) => s.spreadsheet_id && s.sheet_name)
  if (!validSheets.length) { ElMessage.error('请配置至少一组有效的表格配置'); return }
  const parsedParams = params.value.map((p) => parseJsonArray(p)).filter((a) => a && a.length > 0)
  if (!parsedParams.length) { ElMessage.error('请至少输入一组参数'); return }

  submitting.value = true
  try {
    const res = await batchCreateTasks({
      name: form.base_task_name,
      description: form.description || '',
      config: {
        base_task_name: form.base_task_name,
        task_description: form.description || '',
        stock_codes: stockCodes.value,
        end_date: form.end_date || null,
        market_type: form.market_type,
        kline_adjustment: form.kline_adjustment,
        token_type: form.token_type,
        token_id: form.token_type === 'file' ? form.token_id : null,
        token_file: '',
        token_json: form.token_json,
        proxy_url: form.proxy_url || null,
        parameters: parsedParams,
        sheets: validSheets.map((s) => ({ spreadsheet_id: s.spreadsheet_id, title: s.title, sheet_name: s.sheet_name }))
      }
    })
    ElMessage.success(`批量任务创建成功，共 ${res.total_created || 0} 个子任务`)
    clearSaved()
    setTimeout(() => router.push('/task/list?version=c31'), 800)
  } catch (e) {
    ElMessage.error(e?.response?.data?.message || '创建批量任务失败')
  } finally {
    submitting.value = false
  }
}

async function doSaveTemplate() {
  if (!templateForm.name.trim()) { ElMessage.warning('请输入模板名称'); return }
  const parsedParams = params.value.map((param) => parseJsonArray(param)).filter((value) => value && value.length > 0)
  if (!form.base_task_name.trim()) { ElMessage.error('请输入任务 Base Name'); return }
  if (!stockCodes.value.length) { ElMessage.error('请至少输入一个股票代码'); return }

  savingTemplate.value = true
  try {
    await createTemplate({
      name: templateForm.name.trim(),
      description: templateForm.description.trim(),
      config: {
        task_type: 'google_sheet_C31',
        base_task_name: form.base_task_name,
        task_description: form.description || '',
        stock_codes: stockCodes.value,
        end_date: form.end_date || null,
        market_type: form.market_type,
        kline_adjustment: form.kline_adjustment,
        token_type: form.token_type,
        token_id: form.token_type === 'file' ? form.token_id : null,
        token_json: form.token_json,
        proxy_url: form.proxy_url || null,
        parameters: parsedParams,
        sheets: sheetConfigs.value.filter((sheet) => sheet.spreadsheet_id && sheet.sheet_name)
      }
    })
    ElMessage.success('模板保存成功')
    saveTemplateVisible.value = false
    templateForm.name = ''
    templateForm.description = ''
    await loadTemplates()
  } catch {
    ElMessage.error('保存模板失败')
  } finally {
    savingTemplate.value = false
  }
}

watch([form, sheetConfigs, stockCodes, params], saveFormData, { deep: true })

onMounted(async () => {
  await Promise.all([loadSheets(), loadTokens(), loadTemplates()])
  const { template_id, restart_task_id } = route.query
  if (template_id) {
    selectedTemplate.value = template_id
    await applyTemplate(template_id)
  } else if (restart_task_id) {
    await loadRestartTask(restart_task_id)
  } else {
    loadSavedFormData()
  }
})
</script>

<style scoped>
.full-width {
  width: 100%;
}

.task-create-batch__sheet-card {
  margin-bottom: 12px;
}

.task-create-batch__sheet-head {
  margin-bottom: 8px;
}

.task-create-batch__sheet-title,
.task-create-batch__param-title {
  color: var(--app-text);
  font-size: 13px;
  font-weight: 700;
}

.task-create-batch__field-note,
.task-create-batch__intro {
  margin-top: 4px;
}

.task-create-batch__sheet-actions {
  justify-content: center;
  margin-bottom: 12px;
}

.task-create-batch__collapse {
  margin-top: 8px;
}

.task-create-batch__field-gap {
  margin-bottom: 8px;
}

.task-create-batch__param-col {
  margin-bottom: 12px;
}

.task-create-batch__param-card {
  height: 100%;
}

.task-create-batch__summary {
  justify-content: center;
}
</style>
