<template>
  <div class="app-page task-create-c5">
    <div class="page-toolbar">
      <div class="page-toolbar__meta">
        <div class="page-toolbar__eyebrow">Task Builder</div>
        <h2 class="page-title">{{ pageTitle }}</h2>
        <p class="page-description">
          按多组 Sheet、产品代码和价格维度创建 C5 任务，适合多表批量抓取与扩展参数执行。
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
            <el-input v-model="form.description" type="textarea" :rows="1" placeholder="可选，用于备注本次任务" />
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
        class="sub-card task-create-c5__sheet-card"
      >
        <div class="section-heading task-create-c5__sheet-head">
          <div>
            <div class="task-create-c5__sheet-title">表格配置 {{ idx + 1 }}</div>
            <div class="panel-note">选择已登记的 Google Sheet，并为每组配置独立工作表。</div>
          </div>
          <el-button v-if="idx > 0" link type="danger" size="small" @click="removeSheet(idx)">移除</el-button>
        </div>

        <el-row :gutter="12">
          <el-col :xs="24" :sm="10">
            <el-form-item label="选择 Google Sheet">
              <el-select
                v-model="sheet.spreadsheet_id"
                placeholder="请选择"
                filterable
                class="full-width"
                @change="loadWorksheetsForSheet(idx)"
              >
                <el-option
                  v-for="s in sheets"
                  :key="s.spreadsheet_id"
                  :value="s.spreadsheet_id"
                  :label="`${s.name} (${s.spreadsheet_id})`"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="7">
            <el-form-item label="表标题">
              <el-input v-model="sheet.title" placeholder="自动带出，可按需修改" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="7">
            <el-form-item label="工作表名称">
              <el-select v-model="sheet.sheet_name" placeholder="先选择 Sheet" class="full-width">
                <el-option v-for="w in sheet.worksheets || []" :key="w" :value="w" :label="w" />
                <el-option value="__custom__" label="自定义输入" />
              </el-select>
              <el-input
                v-if="sheet.sheet_name === '__custom__'"
                v-model="sheet.custom_sheet_name"
                class="task-create-c5__field-gap"
                placeholder="输入工作表名称"
              />
            </el-form-item>
          </el-col>
        </el-row>
      </div>

      <el-collapse v-model="advancedOpen" class="task-create-c5__collapse">
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
                  class="full-width task-create-c5__field-gap"
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
                  <el-input v-model="tokenImportPath" placeholder="输入 Token 文件路径后导入" />
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
        <h3 class="section-title section-title--muted">产品与参数配置</h3>
      </div>

      <el-row :gutter="16">
        <el-col :xs="24" :lg="8">
          <div class="sub-card task-create-c5__config-card">
            <div class="task-create-c5__config-title">统计方式</div>
            <el-radio-group v-model="form.count_mode">
              <el-radio-button value="total">总数</el-radio-button>
              <el-radio-button value="n_plus_1">N+1</el-radio-button>
            </el-radio-group>
            <div class="panel-note task-create-c5__note">N+1 模式可开启整年 / 近年区间。</div>
          </div>
        </el-col>
        <el-col :xs="24" :lg="8">
          <div class="sub-card task-create-c5__config-card">
            <div class="task-create-c5__config-title">市场类型</div>
            <el-radio-group v-model="form.market_type">
              <el-radio-button value="us">美股</el-radio-button>
              <el-radio-button value="cn">A股</el-radio-button>
            </el-radio-group>
            <div class="panel-note task-create-c5__note">统一影响代码和时间区间的执行上下文。</div>
          </div>
        </el-col>
        <el-col :xs="24" :lg="8">
          <div class="sub-card task-create-c5__config-card">
            <div class="task-create-c5__config-title">价格模式</div>
            <el-radio-group v-model="form.price_mode">
              <el-radio-button value="kp_price">开盘价</el-radio-button>
              <el-radio-button value="sp_price">收盘价</el-radio-button>
            </el-radio-group>
            <div class="panel-note task-create-c5__note">用于结果计算时的价格来源。</div>
          </div>
        </el-col>
      </el-row>

      <div class="sub-card task-create-c5__range-card">
        <div class="section-heading task-create-c5__range-head">
          <div>
            <div class="task-create-c5__config-title">日期范围</div>
            <div class="panel-note">开始和结束日期会随任务模板一起保存。</div>
          </div>
          <div class="control-row">
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

        <el-row :gutter="16">
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

        <div v-if="dateRangeRecent" class="task-create-c5__exclude-wrap">
          <div class="task-create-c5__config-title">排除年份</div>
          <div class="tag-wall">
            <el-checkbox v-for="year in 10" :key="year" v-model="excludeYears" :label="year">
              {{ year }}年
            </el-checkbox>
          </div>
        </div>
      </div>

      <div class="task-create-c5__product-block">
        <div class="section-heading task-create-c5__product-head">
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
        <div class="tag-wall task-create-c5__tag-wall">
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

      <el-row :gutter="16" class="task-create-c5__param-row">
        <el-col :xs="24" :md="12">
          <div class="sub-card task-create-c5__param-card">
            <div class="task-create-c5__config-title">参数 2</div>
            <el-input v-model="param2" type="textarea" :rows="4" placeholder='["value1", "value2"]' />
            <div class="panel-note task-create-c5__note">JSON 数组格式，可选。</div>
          </div>
        </el-col>
        <el-col :xs="24" :md="12">
          <div class="sub-card task-create-c5__param-card">
            <div class="task-create-c5__config-title">参数 3</div>
            <el-input v-model="param3" type="textarea" :rows="4" placeholder='["value1", "value2"]' />
            <div class="panel-note task-create-c5__note">JSON 数组格式，可选。</div>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <el-card v-if="productCodes.length > 0" shadow="never" class="page-section">
      <div class="info-banner task-create-c5__summary">
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
import {
  getGoogleSheets,
  getWorksheets,
  getTokens,
  importToken as apiImportToken
} from '@/api/googleSheet'
import { createTask, getTask } from '@/api/task'
import { getTemplates, getTemplate, createTemplate } from '@/api/template'
import { useResponsive } from '@/composables/useResponsive'

const route = useRoute()
const router = useRouter()
const { isMobile } = useResponsive()

const RANDOM_TOKEN = '__random__'
const LS_KEY = 'google_sheet_c5_form_data'

const pageTitle = ref('创建新任务 (C5)')
const sheets = ref([])
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
const excludeYears = ref([])
const param2 = ref('')
const param3 = ref('')

const form = reactive({
  name: '',
  description: '',
  token_type: 'file',
  token_id: RANDOM_TOKEN,
  token_json: '',
  proxy_url: '',
  count_mode: 'total',
  market_type: 'cn',
  price_mode: 'kp_price',
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

function parseJsonArray(str) {
  if (!str || !str.trim()) return []
  try {
    const value = JSON.parse(str)
    return Array.isArray(value) ? value : []
  } catch {
    return []
  }
}

async function loadSheets() {
  try {
    const res = await getGoogleSheets({ only_available: 1, table_type: 'c5' })
    sheets.value = res.items || []
  } catch {}
}

async function loadTokens() {
  try {
    const res = await getTokens()
    tokens.value = res.tokens || []
  } catch {}
}

async function loadTemplates() {
  try {
    const res = await getTemplates({ task_type: 'google_sheet_C5' })
    templates.value = res.templates || []
  } catch {}
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
  if (!sheet.spreadsheet_id) return

  try {
    const res = await getWorksheets({
      spreadsheet_id: sheet.spreadsheet_id,
      token_id: form.token_id,
      proxy_url: form.proxy_url || undefined
    })
    sheet.worksheets = res.worksheets || []
    if (res.title) sheet.title = res.title
    if (sheet.worksheets.length) sheet.sheet_name = sheet.worksheets[0]
    ElMessage.success('工作表已加载')
  } catch {
    ElMessage.error('获取工作表失败')
  }
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

function applyConfig(config, name) {
  if (name) form.name = name
  if (config.token_type) form.token_type = config.token_type
  if (config.token_id) form.token_id = String(config.token_id)
  if (config.token_json) form.token_json = config.token_json
  if (config.proxy_url) form.proxy_url = config.proxy_url
  if (config.count_mode) form.count_mode = config.count_mode
  if (config.market_type) form.market_type = config.market_type
  if (config.price_mode) form.price_mode = config.price_mode
  if (config.start_date) form.start_date = config.start_date
  if (config.end_date) form.end_date = config.end_date

  if (Array.isArray(config.date_range_mode)) {
    dateRangeFull.value = config.date_range_mode.includes('full')
    dateRangeRecent.value = config.date_range_mode.includes('recent')
  }

  if (Array.isArray(config.exclude_years)) excludeYears.value = config.exclude_years

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

  if (Array.isArray(config.parameters)) {
    if (config.parameters[0]) productCodes.value = config.parameters[0]
    if (config.parameters[1]) param2.value = JSON.stringify(config.parameters[1])
    if (config.parameters[2]) param3.value = JSON.stringify(config.parameters[2])
  }
}

async function applyTemplate(id) {
  if (!id) return

  try {
    const tpl = await getTemplate(id)
    const config = typeof tpl.config === 'string' ? JSON.parse(tpl.config) : tpl.config || {}
    applyConfig(config, tpl.name)
    ElMessage.success('模板配置已加载')
  } catch {
    ElMessage.error('加载模板失败')
  }
}

async function loadRestartTask(taskId) {
  try {
    const res = await getTask(taskId)
    const task = res.task || res
    const config = task.config || {}
    pageTitle.value = '重启任务 (C5)'
    applyConfig(config, task.name ? `${task.name} (重启)` : '')
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
        dateRangeRecent: dateRangeRecent.value,
        excludeYears: excludeYears.value,
        param2: param2.value,
        param3: param3.value
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
      price_mode: data.price_mode || 'kp_price',
      start_date: data.start_date || '',
      end_date: data.end_date || ''
    })

    if (Array.isArray(data.sheetConfigs)) {
      sheetConfigs.value = data.sheetConfigs.map((sheet) => ({ ...sheet, worksheets: [] }))
    }
    if (Array.isArray(data.productCodes)) productCodes.value = data.productCodes
    if (data.dateRangeFull !== undefined) dateRangeFull.value = data.dateRangeFull
    if (data.dateRangeRecent !== undefined) dateRangeRecent.value = data.dateRangeRecent
    if (Array.isArray(data.excludeYears)) excludeYears.value = data.excludeYears
    if (data.param2) param2.value = data.param2
    if (data.param3) param3.value = data.param3

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
    price_mode: 'kp_price',
    start_date: '',
    end_date: ''
  })
  sheetConfigs.value = [
    { spreadsheet_id: '', title: '', sheet_name: '', custom_sheet_name: '', worksheets: [] }
  ]
  productCodes.value = []
  dateRangeFull.value = false
  dateRangeRecent.value = false
  excludeYears.value = []
  param2.value = ''
  param3.value = ''
  ElMessage.success('已清除保存的表单数据')
}

async function submit() {
  if (!productCodes.value.length) {
    ElMessage.error('请至少输入一个产品代码')
    return
  }

  const primarySheet = sheetConfigs.value[0]
  if (!primarySheet.spreadsheet_id) {
    ElMessage.error('请选择 Google Sheet')
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

  const sheetsPayload = sheetConfigs.value
    .filter((sheet) => sheet.spreadsheet_id)
    .map((sheet, index) => {
      const sheetName =
        sheet.sheet_name === '__custom__' ? sheet.custom_sheet_name : sheet.sheet_name
      const result = { spreadsheet_id: sheet.spreadsheet_id, sheet_name: sheetName }
      if (index === 0 && sheet.title) result.title = sheet.title
      return result
    })
    .filter((sheet) => sheet.spreadsheet_id && sheet.sheet_name)

  if (!sheetsPayload.length) {
    ElMessage.error('请至少配置一组有效的表格')
    return
  }

  const dateRangeModes = []
  if (dateRangeFull.value) dateRangeModes.push('full')
  if (dateRangeRecent.value) dateRangeModes.push('recent')

  const parameters = [productCodes.value]
  const parsedParam2 = parseJsonArray(param2.value)
  const parsedParam3 = parseJsonArray(param3.value)
  if (parsedParam2.length) parameters.push(parsedParam2)
  if (parsedParam3.length) {
    if (!parsedParam2.length) parameters.push([])
    parameters.push(parsedParam3)
  }

  submitting.value = true
  try {
    const res = await createTask({
      name: form.name || `Google Sheet C5 任务 - ${new Date().toLocaleString()}`,
      description: form.description || `批量执行 ${productCodes.value.length} 个产品代码`,
      task_type: 'google_sheet_C5',
      config: {
        token_type: form.token_type,
        token_id: form.token_type === 'file' ? form.token_id : null,
        token_file: '',
        token_json: form.token_json,
        proxy_url: form.proxy_url || null,
        count_mode: form.count_mode,
        market_type: form.market_type,
        price_mode: form.price_mode,
        date_range_mode: dateRangeModes.length ? dateRangeModes : ['full'],
        start_date: form.start_date || null,
        end_date: form.end_date || null,
        exclude_years: dateRangeRecent.value ? excludeYears.value : [],
        parameters,
        sheets: sheetsPayload
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

  const sheetsPayload = sheetConfigs.value
    .filter((sheet) => sheet.spreadsheet_id)
    .map((sheet) => ({
      spreadsheet_id: sheet.spreadsheet_id,
      sheet_name: sheet.sheet_name === '__custom__' ? sheet.custom_sheet_name : sheet.sheet_name,
      title: sheet.title
    }))

  const dateRangeModes = []
  if (dateRangeFull.value) dateRangeModes.push('full')
  if (dateRangeRecent.value) dateRangeModes.push('recent')

  const parameters = [productCodes.value]
  const parsedParam2 = parseJsonArray(param2.value)
  const parsedParam3 = parseJsonArray(param3.value)
  if (parsedParam2.length) parameters.push(parsedParam2)
  if (parsedParam3.length) {
    if (!parsedParam2.length) parameters.push([])
    parameters.push(parsedParam3)
  }

  savingTemplate.value = true
  try {
    await createTemplate({
      name: templateForm.name,
      description: templateForm.description,
      config: {
        task_type: 'google_sheet_C5',
        token_type: form.token_type,
        token_id: form.token_id,
        token_json: form.token_json,
        proxy_url: form.proxy_url,
        count_mode: form.count_mode,
        market_type: form.market_type,
        price_mode: form.price_mode,
        date_range_mode: dateRangeModes,
        start_date: form.start_date,
        end_date: form.end_date,
        exclude_years: excludeYears.value,
        parameters,
        sheets: sheetsPayload
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

watch(
  [form, sheetConfigs, productCodes, dateRangeFull, dateRangeRecent, excludeYears, param2, param3],
  saveFormData,
  { deep: true }
)

onMounted(async () => {
  await Promise.all([loadSheets(), loadTokens(), loadTemplates()])
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

.task-create-c5__sheet-card {
  margin-bottom: 12px;
}

.task-create-c5__sheet-head {
  margin-bottom: 8px;
}

.task-create-c5__sheet-title,
.task-create-c5__config-title {
  color: var(--app-text);
  font-size: 13px;
  font-weight: 700;
}

.task-create-c5__collapse {
  margin-top: 8px;
}

.task-create-c5__field-gap {
  margin-top: 8px;
}

.task-create-c5__config-card,
.task-create-c5__param-card {
  height: 100%;
}

.task-create-c5__note {
  margin-top: 8px;
}

.task-create-c5__range-card,
.task-create-c5__product-block,
.task-create-c5__param-row {
  margin-top: 16px;
}

.task-create-c5__range-head,
.task-create-c5__product-head {
  margin-bottom: 8px;
}

.task-create-c5__exclude-wrap {
  margin-top: 8px;
}

.task-create-c5__tag-wall {
  margin-top: 8px;
}

.task-create-c5__summary {
  justify-content: center;
}
</style>
