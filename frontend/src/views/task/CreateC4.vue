<template>
  <div class="app-page task-create-c4">
    <div class="page-toolbar">
      <div class="page-toolbar__meta">
        <div class="page-toolbar__eyebrow">Task Builder</div>
        <h2 class="page-title">{{ pageTitle }}</h2>
        <p class="page-description">
          按产品代码、时间范围和多组 Sheet 配置创建 C4 任务，适合批量抓取与统一执行。
        </p>
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
        <el-col :xs="24" :sm="8">
          <el-form-item label="选择模板">
            <el-select
              v-model="selectedTemplate"
              placeholder="不使用模板"
              clearable
              class="full-width"
              @change="applyTemplate"
            >
              <el-option v-for="t in templates" :key="t.id" :value="t.id" :label="t.name" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :xs="24" :sm="8">
          <el-form-item label="任务名称">
            <el-input v-model="form.name" placeholder="留空将自动生成" />
          </el-form-item>
        </el-col>
        <el-col :xs="24" :sm="8">
          <el-form-item label="任务描述">
            <el-input v-model="form.description" type="textarea" :rows="1" placeholder="可选，用于备注本次任务范围" />
          </el-form-item>
        </el-col>
      </el-row>
    </el-card>

    <el-card shadow="never" class="page-section">
      <div class="section-heading">
        <h3 class="section-title section-title--muted">Google Sheet 配置</h3>
        <div class="section-actions">
          <el-button size="small" @click="addSheet">添加一组表格</el-button>
          <el-button
            size="small"
            type="danger"
            plain
            :disabled="sheetConfigs.length <= 1"
            @click="removeSheet(sheetConfigs.length - 1)"
          >
            移除最后一组
          </el-button>
        </div>
      </div>

      <div
        v-for="(sheet, idx) in sheetConfigs"
        :key="idx"
        class="sub-card task-create-c4__sheet-card"
      >
        <div class="section-heading task-create-c4__sheet-head">
          <div>
            <div class="task-create-c4__sheet-title">表格配置 {{ idx + 1 }}</div>
            <div class="panel-note">支持直接输入 Spreadsheet ID 或完整 Google Sheet 链接。</div>
          </div>
          <el-button v-if="idx > 0" link type="danger" size="small" @click="removeSheet(idx)">移除</el-button>
        </div>

        <el-row :gutter="12">
          <el-col :xs="24" :sm="8">
            <el-form-item label="Spreadsheet ID">
              <el-input
                v-model="sheet.spreadsheet_id"
                placeholder="输入 ID 或 URL"
                @change="loadWorksheetsForSheet(idx)"
              />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="8">
            <el-form-item label="表标题">
              <el-input v-model="sheet.title" placeholder="可选，用于主表展示名" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="8">
            <el-form-item label="工作表名称">
              <el-select v-model="sheet.sheet_name" placeholder="先输入 ID 再加载工作表" class="full-width">
                <el-option v-for="w in sheet.worksheets || []" :key="w" :value="w" :label="w" />
                <el-option value="__custom__" label="自定义输入" />
              </el-select>
              <el-input
                v-if="sheet.sheet_name === '__custom__'"
                v-model="sheet.custom_sheet_name"
                class="task-create-c4__field-gap"
                placeholder="输入工作表名称"
              />
            </el-form-item>
          </el-col>
        </el-row>
      </div>

      <el-collapse v-model="advancedOpen" class="task-create-c4__collapse">
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
                <el-select
                  v-model="form.token_id"
                  class="full-width task-create-c4__field-gap"
                  placeholder="选择 Token"
                >
                  <el-option
                    :value="RANDOM_TOKEN"
                    label="随机 Token（系统自动选择未达上限的 Token）"
                  />
                  <el-option
                    v-for="t in tokens"
                    :key="t.id"
                    :value="String(t.id)"
                    :label="`${t.name} | 占用 ${t.current_in_use_count || 0} | 累计 ${t.task_usage_count} | 上限 ${t.max_usage_count > 0 ? t.max_usage_count : '无限'}`"
                    :disabled="!t.is_available"
                  />
                </el-select>
                <div class="control-row control-row--stretch">
                  <el-input
                    v-model="tokenImportPath"
                    placeholder="输入 Token 文件路径后导入"
                  />
                  <el-button @click="doImportToken">导入</el-button>
                </div>
              </el-form-item>
            </el-col>
            <el-col v-else :xs="24" :sm="18">
              <el-form-item label="Token JSON">
                <el-input
                  v-model="form.token_json"
                  type="textarea"
                  :rows="3"
                  placeholder='{"installed": {...}}'
                />
              </el-form-item>
            </el-col>
            <el-col :xs="24" :sm="12">
              <el-form-item label="代理 URL">
                <el-input v-model="form.proxy_url" placeholder="可选，例如 http://127.0.0.1:7890" />
              </el-form-item>
            </el-col>
          </el-row>
        </el-collapse-item>
      </el-collapse>
    </el-card>

    <el-card shadow="never" class="page-section">
      <div class="section-heading">
        <h3 class="section-title section-title--muted">产品与时间配置</h3>
      </div>

      <el-row :gutter="16">
        <el-col :xs="24" :lg="10">
          <div class="sub-card task-create-c4__config-card">
            <div class="task-create-c4__config-title">统计维度</div>
            <div class="control-row">
              <el-radio-group v-model="form.count_mode">
                <el-radio-button value="total">总数</el-radio-button>
                <el-radio-button value="n_plus_1">N+1</el-radio-button>
              </el-radio-group>
            </div>
            <div class="panel-note">N+1 模式下可启用整年 / 近年范围选择。</div>
          </div>
        </el-col>

        <el-col :xs="24" :lg="14">
          <div class="sub-card task-create-c4__config-card">
            <div class="task-create-c4__config-title">市场与日期</div>
            <el-row :gutter="12">
              <el-col :xs="24" :sm="8">
                <el-form-item label="市场类型">
                  <el-radio-group v-model="form.market_type">
                    <el-radio-button value="us">美股</el-radio-button>
                    <el-radio-button value="cn">A股</el-radio-button>
                  </el-radio-group>
                </el-form-item>
              </el-col>
              <el-col :xs="24" :sm="8">
                <el-form-item label="开始日期">
                  <el-date-picker
                    v-model="form.start_date"
                    type="date"
                    value-format="YYYY-MM-DD"
                    class="full-width"
                  />
                </el-form-item>
              </el-col>
              <el-col :xs="24" :sm="8">
                <el-form-item label="结束日期">
                  <el-date-picker
                    v-model="form.end_date"
                    type="date"
                    value-format="YYYY-MM-DD"
                    class="full-width"
                  />
                </el-form-item>
              </el-col>
            </el-row>
            <div class="control-row task-create-c4__date-mode">
              <el-checkbox
                v-model="dateRangeFull"
                :disabled="form.count_mode !== 'n_plus_1'"
                label="整年"
              />
              <el-checkbox
                v-model="dateRangeRecent"
                :disabled="form.count_mode !== 'n_plus_1'"
                label="近年"
              />
            </div>
          </div>
        </el-col>
      </el-row>

      <div class="task-create-c4__product-block">
        <div class="section-heading task-create-c4__product-head">
          <h3 class="section-title section-title--muted">股票 / 产品代码</h3>
          <div class="section-actions">
            <el-tag type="info">{{ productCodes.length }} 个</el-tag>
          </div>
        </div>
        <div class="control-row control-row--stretch">
          <el-input
            v-model="productCodeInput"
            placeholder="例如 600000,600001 或 AAPL MSFT"
            @keyup.enter="addProductCodes"
          />
          <el-button @click="addProductCodes">添加</el-button>
        </div>
        <div class="tag-wall task-create-c4__tag-wall">
          <el-tag
            v-for="code in productCodes"
            :key="code"
            closable
            @close="removeProductCode(code)"
          >
            {{ code }}
          </el-tag>
          <span v-if="!productCodes.length" class="panel-note">暂无产品代码</span>
        </div>
      </div>
    </el-card>

    <el-card v-if="productCodes.length > 0" shadow="never" class="page-section">
      <div class="info-banner task-create-c4__summary">
        <span>
          <el-tag type="primary">{{ productCodes.length }}</el-tag> 个产品代码，
          <el-tag type="warning">{{ validSheetCount }}</el-tag> 组有效 Sheet 配置，
          日期模式：
          <strong>{{ dateRangeModeLabel }}</strong>
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

    <el-dialog
      v-model="saveTemplateVisible"
      title="保存为模板"
      width="480px"
      :fullscreen="isMobile"
    >
      <el-form label-width="80px">
        <el-form-item label="模板名称">
          <el-input v-model="templateForm.name" />
        </el-form-item>
        <el-form-item label="模板描述">
          <el-input v-model="templateForm.description" type="textarea" :rows="2" />
        </el-form-item>
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
import { getWorksheets, getTokens, importToken as apiImportToken } from '@/api/googleSheet'
import { createTask, getTask } from '@/api/task'
import { getTemplates, getTemplate, createTemplate } from '@/api/template'
import { useResponsive } from '@/composables/useResponsive'

const route = useRoute()
const router = useRouter()
const { isMobile } = useResponsive()

const RANDOM_TOKEN = '__random__'
const LS_KEY = 'google_sheet_c4_form_data'

const pageTitle = ref('创建新任务 (C4)')
const tokens = ref([])
const templates = ref([])
const selectedTemplate = ref('')
const advancedOpen = ref([])
const submitting = ref(false)
const saveTemplateVisible = ref(false)
const savingTemplate = ref(false)
const tokenImportPath = ref('')
const productCodeInput = ref('')
const productCodes = ref([])
const dateRangeFull = ref(false)
const dateRangeRecent = ref(false)

const form = reactive({
  name: '',
  description: '',
  token_type: 'file',
  token_id: RANDOM_TOKEN,
  token_json: '',
  proxy_url: '',
  count_mode: 'total',
  market_type: 'cn',
  start_date: '',
  end_date: ''
})

const sheetConfigs = ref([
  { spreadsheet_id: '', title: '', sheet_name: '', custom_sheet_name: '', worksheets: [] }
])
const templateForm = reactive({ name: '', description: '' })

const validSheetCount = computed(() =>
  sheetConfigs.value.filter((sheet) => {
    const sheetName = sheet.sheet_name === '__custom__' ? sheet.custom_sheet_name : sheet.sheet_name
    return Boolean(sheet.spreadsheet_id && sheetName)
  }).length
)

const dateRangeModeLabel = computed(() => {
  const labels = []
  if (dateRangeFull.value) labels.push('整年')
  if (dateRangeRecent.value) labels.push('近年')
  return labels.length ? labels.join(' / ') : '默认整年'
})

function normalizeC4Config(raw) {
  if (!raw || typeof raw !== 'object') return {}
  if (Array.isArray(raw.sheets) && raw.sheets.length) return raw

  const sheets = []
  if (raw.spreadsheet_id) {
    sheets.push({
      spreadsheet_id: raw.spreadsheet_id,
      sheet_name: raw.sheet_name || '',
      title: raw.title || raw.spreadsheet_title || ''
    })
  }

  return { ...raw, sheets }
}

function extractSpreadsheetId(input) {
  if (!input) return ''
  const match = input.match(/\/spreadsheets\/d\/([a-zA-Z0-9-_]+)/)
  return match ? match[1] : input.trim()
}

function addSheet() {
  sheetConfigs.value.push({
    spreadsheet_id: '',
    title: '',
    sheet_name: '',
    custom_sheet_name: '',
    worksheets: []
  })
}

function removeSheet(idx) {
  if (sheetConfigs.value.length <= 1) {
    ElMessage.info('至少保留一组表格配置')
    return
  }
  sheetConfigs.value.splice(idx, 1)
}

async function loadWorksheetsForSheet(idx) {
  const sheet = sheetConfigs.value[idx]
  const spreadsheetId = extractSpreadsheetId(sheet.spreadsheet_id)
  if (!spreadsheetId) return

  try {
    const res = await getWorksheets({
      spreadsheet_id: spreadsheetId,
      token_id: form.token_id,
      proxy_url: form.proxy_url || undefined
    })
    sheet.worksheets = res.worksheets || []
    if (res.title && idx === 0) sheet.title = res.title
    if (sheet.worksheets.length) sheet.sheet_name = sheet.worksheets[0]
    ElMessage.success('工作表已加载')
  } catch {
    ElMessage.error('获取工作表失败')
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
    const res = await getTemplates({ task_type: 'google_sheet_C4' })
    templates.value = res.templates || []
  } catch {}
}

function addProductCodes() {
  const parts = productCodeInput.value
    .split(/[,\s]+/)
    .map((part) => part.trim())
    .filter((part) => part)

  if (!parts.length) return

  const set = new Set(productCodes.value)
  parts.forEach((code) => set.add(code))
  productCodes.value = Array.from(set)
  productCodeInput.value = ''
  ElMessage.success(`已添加 ${parts.length} 个产品代码`)
}

function removeProductCode(code) {
  productCodes.value = productCodes.value.filter((item) => item !== code)
}

function initDefaultDates() {
  if (form.start_date || form.end_date) return

  const today = new Date()
  const end = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 1)
  const start = new Date(end.getFullYear() - 5, end.getMonth(), end.getDate())
  const formatDate = (date) =>
    `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`

  form.end_date = formatDate(end)
  form.start_date = formatDate(start)
}

async function applyTemplate(id) {
  if (!id) return

  try {
    const tpl = await getTemplate(id)
    const config = normalizeC4Config(
      typeof tpl.config === 'string' ? JSON.parse(tpl.config) : tpl.config || {}
    )

    if (tpl.name) form.name = tpl.name
    if (config.token_type) form.token_type = config.token_type
    if (config.token_id) form.token_id = String(config.token_id)
    if (config.token_json) form.token_json = config.token_json
    if (config.proxy_url) form.proxy_url = config.proxy_url
    if (config.count_mode) form.count_mode = config.count_mode
    if (config.market_type) form.market_type = config.market_type
    if (config.start_date) form.start_date = config.start_date
    if (config.end_date) form.end_date = config.end_date

    if (Array.isArray(config.date_range_mode)) {
      dateRangeFull.value = config.date_range_mode.includes('full')
      dateRangeRecent.value = config.date_range_mode.includes('recent')
    }

    if (Array.isArray(config.sheets) && config.sheets.length) {
      sheetConfigs.value = config.sheets.map((sheet) => ({
        spreadsheet_id: sheet.spreadsheet_id || '',
        title: sheet.title || '',
        sheet_name: sheet.sheet_name || '',
        custom_sheet_name: '',
        worksheets: []
      }))
    } else if (config.spreadsheet_id) {
      sheetConfigs.value = [
        {
          spreadsheet_id: config.spreadsheet_id,
          title: config.title || '',
          sheet_name: config.sheet_name || '',
          custom_sheet_name: '',
          worksheets: []
        }
      ]
    }

    if (Array.isArray(config.parameters) && config.parameters[0]) {
      productCodes.value = config.parameters[0]
    }

    ElMessage.success('模板配置已加载')
  } catch {
    ElMessage.error('加载模板失败')
  }
}

async function loadRestartTask(taskId) {
  try {
    const res = await getTask(taskId)
    const task = res.task || res
    const config = normalizeC4Config(task.config || {})

    pageTitle.value = '重启任务 (C4)'
    if (task.name) form.name = `${task.name} (重启)`

    Object.assign(form, {
      token_type: config.token_type || 'file',
      token_id: config.token_id ? String(config.token_id) : RANDOM_TOKEN,
      token_json: config.token_json || '',
      proxy_url: config.proxy_url || '',
      count_mode: config.count_mode || 'total',
      market_type: config.market_type || 'cn',
      start_date: config.start_date || '',
      end_date: config.end_date || ''
    })

    dateRangeFull.value = Array.isArray(config.date_range_mode)
      ? config.date_range_mode.includes('full')
      : false
    dateRangeRecent.value = Array.isArray(config.date_range_mode)
      ? config.date_range_mode.includes('recent')
      : false

    if (Array.isArray(config.sheets) && config.sheets.length) {
      sheetConfigs.value = config.sheets.map((sheet) => ({
        spreadsheet_id: sheet.spreadsheet_id || '',
        title: sheet.title || '',
        sheet_name: sheet.sheet_name || '',
        custom_sheet_name: '',
        worksheets: []
      }))
    }

    if (Array.isArray(config.parameters) && config.parameters[0]) {
      productCodes.value = config.parameters[0]
    }

    ElMessage.info('已加载原任务配置')
  } catch {
    ElMessage.error('加载原任务失败')
  }
}

function saveFormData() {
  try {
    localStorage.setItem(
      LS_KEY,
      JSON.stringify({
        ...form,
        sheetConfigs: sheetConfigs.value.map((sheet) => ({
          spreadsheet_id: sheet.spreadsheet_id,
          title: sheet.title,
          sheet_name: sheet.sheet_name,
          custom_sheet_name: sheet.custom_sheet_name
        })),
        productCodes: productCodes.value,
        dateRangeFull: dateRangeFull.value,
        dateRangeRecent: dateRangeRecent.value
      })
    )
  } catch {}
}

function loadSavedFormData() {
  try {
    const saved = localStorage.getItem(LS_KEY)
    if (!saved) return

    const data = JSON.parse(saved)
    Object.assign(form, {
      name: data.name || '',
      description: data.description || '',
      token_type: data.token_type || 'file',
      token_id: data.token_id || RANDOM_TOKEN,
      token_json: data.token_json || '',
      proxy_url: data.proxy_url || '',
      count_mode: data.count_mode || 'total',
      market_type: data.market_type || 'cn',
      start_date: data.start_date || '',
      end_date: data.end_date || ''
    })

    if (Array.isArray(data.sheetConfigs)) {
      sheetConfigs.value = data.sheetConfigs.map((sheet) => ({
        ...sheet,
        worksheets: []
      }))
    }

    if (Array.isArray(data.productCodes)) productCodes.value = data.productCodes
    if (data.dateRangeFull !== undefined) dateRangeFull.value = data.dateRangeFull
    if (data.dateRangeRecent !== undefined) dateRangeRecent.value = data.dateRangeRecent

    ElMessage.info('表单数据已恢复')
  } catch {}
}

function clearSaved() {
  localStorage.removeItem(LS_KEY)
  Object.assign(form, {
    name: '',
    description: '',
    token_type: 'file',
    token_id: RANDOM_TOKEN,
    token_json: '',
    proxy_url: '',
    count_mode: 'total',
    market_type: 'cn',
    start_date: '',
    end_date: ''
  })
  sheetConfigs.value = [
    { spreadsheet_id: '', title: '', sheet_name: '', custom_sheet_name: '', worksheets: [] }
  ]
  productCodes.value = []
  dateRangeFull.value = false
  dateRangeRecent.value = false
  ElMessage.success('已清除保存的表单数据')
}

async function submit() {
  if (!productCodes.value.length) {
    ElMessage.error('请至少输入一个产品代码')
    return
  }

  const primarySheet = sheetConfigs.value[0]
  if (!primarySheet.spreadsheet_id) {
    ElMessage.error('请输入电子表格 ID')
    return
  }

  if (form.token_type === 'file' && !form.token_id) {
    ElMessage.error('请选择 Token')
    return
  }

  if (form.token_type === 'json' && !form.token_json) {
    ElMessage.error('请输入 Token JSON')
    return
  }

  const sheets = sheetConfigs.value
    .filter((sheet) => sheet.spreadsheet_id)
    .map((sheet, index) => {
      const spreadsheetId = extractSpreadsheetId(sheet.spreadsheet_id)
      const sheetName =
        sheet.sheet_name === '__custom__' ? sheet.custom_sheet_name : sheet.sheet_name
      const result = { spreadsheet_id: spreadsheetId, sheet_name: sheetName }
      if (index === 0 && sheet.title) result.title = sheet.title
      return result
    })
    .filter((sheet) => sheet.spreadsheet_id && sheet.sheet_name)

  if (!sheets.length) {
    ElMessage.error('请至少配置一组有效的表格')
    return
  }

  const dateRangeModes = []
  if (dateRangeFull.value) dateRangeModes.push('full')
  if (dateRangeRecent.value) dateRangeModes.push('recent')

  submitting.value = true
  try {
    const res = await createTask({
      name: form.name || `Google Sheet C4 任务 - ${new Date().toLocaleString()}`,
      description: form.description || `批量执行 ${productCodes.value.length} 个产品代码`,
      task_type: 'google_sheet_C4',
      config: {
        token_type: form.token_type,
        token_id: form.token_type === 'file' ? form.token_id : null,
        token_file: '',
        token_json: form.token_json,
        proxy_url: form.proxy_url || null,
        count_mode: form.count_mode,
        market_type: form.market_type,
        date_range_mode: dateRangeModes.length ? dateRangeModes : ['full'],
        start_date: form.start_date || null,
        end_date: form.end_date || null,
        parameters: [productCodes.value],
        sheets
      }
    })

    ElMessage.success('任务创建成功，正在跳转...')
    clearSaved()
    setTimeout(() => router.push(`/task/${res.task_id}`), 800)
  } catch {
    ElMessage.error('创建任务失败')
  } finally {
    submitting.value = false
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

async function doSaveTemplate() {
  if (!templateForm.name) {
    ElMessage.warning('请输入模板名称')
    return
  }

  const sheets = sheetConfigs.value
    .filter((sheet) => sheet.spreadsheet_id)
    .map((sheet) => ({
      spreadsheet_id: extractSpreadsheetId(sheet.spreadsheet_id),
      sheet_name: sheet.sheet_name === '__custom__' ? sheet.custom_sheet_name : sheet.sheet_name,
      title: sheet.title
    }))

  const dateRangeModes = []
  if (dateRangeFull.value) dateRangeModes.push('full')
  if (dateRangeRecent.value) dateRangeModes.push('recent')

  savingTemplate.value = true
  try {
    await createTemplate({
      name: templateForm.name,
      description: templateForm.description,
      config: {
        task_type: 'google_sheet_C4',
        token_type: form.token_type,
        token_id: form.token_id,
        token_json: form.token_json,
        proxy_url: form.proxy_url,
        count_mode: form.count_mode,
        market_type: form.market_type,
        date_range_mode: dateRangeModes,
        start_date: form.start_date,
        end_date: form.end_date,
        parameters: [productCodes.value],
        sheets
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

watch([form, sheetConfigs, productCodes, dateRangeFull, dateRangeRecent], saveFormData, {
  deep: true
})

onMounted(async () => {
  await Promise.all([loadTokens(), loadTemplates()])
  initDefaultDates()
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

.task-create-c4__sheet-card {
  margin-bottom: 12px;
}

.task-create-c4__sheet-head {
  margin-bottom: 8px;
}

.task-create-c4__sheet-title,
.task-create-c4__config-title {
  color: var(--app-text);
  font-size: 13px;
  font-weight: 700;
}

.task-create-c4__collapse {
  margin-top: 8px;
}

.task-create-c4__field-gap {
  margin-top: 8px;
}

.task-create-c4__config-card {
  height: 100%;
}

.task-create-c4__date-mode {
  margin-top: 4px;
}

.task-create-c4__product-block {
  margin-top: 16px;
}

.task-create-c4__product-head {
  margin-bottom: 8px;
}

.task-create-c4__tag-wall {
  margin-top: 8px;
}

.task-create-c4__summary {
  justify-content: center;
}
</style>
