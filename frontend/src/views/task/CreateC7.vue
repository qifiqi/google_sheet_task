<template>
  <div class="app-page task-create-c7">
    <div class="page-toolbar">
      <div class="page-toolbar__meta">
        <div class="page-toolbar__eyebrow">Task Builder</div>
        <h2 class="page-title">{{ pageTitle }}</h2>
        <p class="page-description">
          按多组 Sheet、C7 模型版本和自定义 K 线创建 C7 任务，支持 C7.0.2 / C7.0.3 模板混配校验。
        </p>
      </div>
      <div class="page-toolbar__actions">
        <el-button class="page-back-button" @click="$router.back()">返回</el-button>
      </div>
    </div>

    <el-form label-position="top" @submit.prevent>
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
        class="sub-card task-create-c7__sheet-card"
      >
        <div class="section-heading task-create-c7__sheet-head">
          <div>
            <div class="task-create-c7__sheet-title">表格配置 {{ idx + 1 }}</div>
            <div class="panel-note">选择已登记的 Google Sheet，C7 模型版本按表标题自动识别，可手动调整。</div>
          </div>
          <el-button v-if="idx > 0" link type="danger" size="small" @click="removeSheet(idx)">移除</el-button>
        </div>

        <el-row :gutter="12">
          <el-col :xs="24" :sm="9">
            <el-form-item label="选择 Google Sheet">
              <div class="control-row control-row--stretch">
                <el-select
                  v-model="sheet.spreadsheet_id"
                  placeholder="请选择 Google Sheet"
                  filterable
                  class="full-width"
                  @change="onSheetChange(idx)"
                >
                  <el-option
                    v-for="s in sheetOptions"
                    :key="s.spreadsheet_id"
                    :value="s.spreadsheet_id"
                    :label="`${s.name} (${s.spreadsheet_id})`"
                  />
                </el-select>
                <el-button @click="loadSheetOptions">刷新</el-button>
              </div>
              <div class="panel-note">
                {{ sheet.spreadsheet_id ? `已选择 Google Sheet：${sheet.spreadsheet_id}` : '请从列表中选择可用的 Google Sheet' }}
              </div>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="5">
            <el-form-item label="C7 模型版本">
              <el-select v-model="sheet.c7_model_version" class="full-width" @change="onModelVersionChange(idx)">
                <el-option value="c7_0_2" label="C7.0.2（两列K线）" :disabled="versionOptionDisabled('c7_0_2')" />
                <el-option value="c7_0_3" label="C7.0.3（OHLC K线）" :disabled="versionOptionDisabled('c7_0_3')" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="5">
            <el-form-item label="表标题">
              <el-input v-model="sheet.title" placeholder="自动带出，可按需修改" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="5">
            <el-form-item label="工作表名称">
              <div class="control-row control-row--stretch">
                <el-input v-model="sheet.sheet_name" readonly placeholder="选择 Sheet 后自动带出" />
                <el-button :disabled="!sheet.spreadsheet_id" @click="loadWorksheetsForSheet(idx, true)">刷新</el-button>
              </div>
              <div class="panel-note">
                {{ sheet.sheet_name ? `默认使用第一个工作表：${sheet.sheet_name}` : '默认展示接口返回的第一个工作表' }}
              </div>
            </el-form-item>
          </el-col>
        </el-row>
      </div>

      <el-collapse v-model="advancedOpen" class="task-create-c7__collapse">
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
                  class="full-width task-create-c7__field-gap"
                  placeholder="选择 Token"
                >
                  <el-option :value="randomTokenValue" label="随机Token（按最低使用数均衡分配）" />
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

      <div class="sub-card task-create-c7__config-card">
        <div class="task-create-c7__config-title">基础设置</div>
        <el-row :gutter="16">
          <el-col :xs="24" :sm="6">
            <el-form-item label="K线来源">
              <el-radio-group v-model="form.kline_source">
                <el-radio-button value="auto">自动K线</el-radio-button>
                <el-radio-button value="custom">自定义K线</el-radio-button>
              </el-radio-group>
              <div class="panel-note task-create-c7__note">自定义K线直接读取 Sheet 输入列，下方行情字段将禁用。</div>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="6">
            <el-form-item label="统计方式">
              <el-radio-group v-model="form.count_mode" :disabled="isCustomKline">
                <el-radio-button value="total">总数</el-radio-button>
                <el-radio-button value="n_plus_1">N+1</el-radio-button>
              </el-radio-group>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="6">
            <el-form-item label="价格类型">
              <el-select v-model="form.price_mode" :disabled="priceModeDisabled" class="full-width">
                <el-option value="vwap_price" label="加权平均价" />
                <el-option value="kp_price" label="开盘价" />
                <el-option value="sp_price" label="收盘价" />
                <el-option value="random_price" label="随机价" />
                <el-option value="ohlc_price" label="OHLC（开高低收）" :disabled="!forceOhlcPrice" />
              </el-select>
              <div v-if="forceOhlcPrice" class="panel-note task-create-c7__note">
                C7.0.3 固定使用 OHLC（开高低收）价格
              </div>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="6">
            <el-form-item label="市场类型">
              <el-select v-model="form.market_type" :disabled="isCustomKline" class="full-width">
                <el-option v-for="m in marketOptions" :key="m.value" :value="m.value" :label="m.label" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-row v-if="showRandomOptions" :gutter="16">
          <el-col :xs="24" :sm="6">
            <el-form-item label="随机价格范围">
              <el-select v-model="form.random_price_range" class="full-width">
                <el-option value="high_low" label="最高价 - 最低价" />
                <el-option value="open_close" label="开盘价 - 收盘价" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="6">
            <el-form-item label="随机组数">
              <el-input-number v-model="form.random_group_count" :min="1" :step="1" class="full-width" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="16">
          <el-col :xs="24" :sm="6">
            <el-form-item label="K线复权">
              <el-select v-model="form.kline_adjustment" :disabled="isCustomKline" class="full-width">
                <el-option value="forward" label="前复权" />
                <el-option value="back" label="后复权" />
                <el-option value="none" label="不复权" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="6">
            <el-form-item label="K线数据源">
              <el-select v-model="form.kline_data_source" class="full-width">
                <el-option value="akshare" label="AKShare（默认）" />
                <el-option value="dfcf" label="东方财富" />
                <el-option value="qq" label="腾讯" />
                <el-option value="yahoo" label="Yahoo" />
                <el-option value="tdx" label="通达信（仅A股）" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="快速时间范围">
              <el-checkbox v-model="dateRangeFull" :disabled="!dateRangeEnabled" label="整年" />
              <el-checkbox v-model="dateRangeRecent" :disabled="!dateRangeEnabled" label="近年" />
            </el-form-item>
          </el-col>
        </el-row>

        <div v-if="dateRangeRecent" class="task-create-c7__exclude-wrap">
          <div class="task-create-c7__config-title">选择要移除的近年区间</div>
          <el-checkbox-group v-model="excludeYears">
            <el-checkbox
              v-for="opt in recentYearOptions"
              :key="opt.value"
              :label="opt.value"
              :disabled="!recentYearsEnabled"
            >
              {{ opt.label }}
            </el-checkbox>
          </el-checkbox-group>
          <div class="panel-note">勾选的年份区间将被移除，不参与计算</div>
        </div>
      </div>

      <div class="sub-card task-create-c7__range-card">
        <div class="task-create-c7__config-title">时间范围设置</div>
        <el-row :gutter="16">
          <el-col :xs="24" :sm="8">
            <el-form-item label="开始日期">
              <el-date-picker
                v-model="form.start_date"
                type="date"
                value-format="YYYY-MM-DD"
                :disabled="isCustomKline"
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
                :disabled="isCustomKline"
                class="full-width"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <div class="panel-note">结束日期默认昨天，开始日期默认结束日期往前推5年，可根据需要修改。</div>
      </div>

      <div class="task-create-c7__product-block">
        <div class="section-heading task-create-c7__product-head">
          <h3 class="section-title section-title--muted">股票 / 产品代码</h3>
          <div class="section-actions">
            <el-tag type="info">{{ productCodes.length }} 个</el-tag>
          </div>
        </div>
        <div class="control-row control-row--stretch">
          <el-input
            v-model="productCodeInput"
            placeholder="如：600000,600001 或 600000 600001"
            @keyup.enter="addProductCodes"
          />
          <el-button @click="addProductCodes">添加</el-button>
        </div>
        <div class="tag-wall task-create-c7__tag-wall">
          <el-tag
            v-for="code in productCodes"
            :key="code"
            closable
            @close="removeProductCode(code)"
          >
            {{ code }}
          </el-tag>
          <span v-if="!productCodes.length" class="panel-note">暂无产品代码，支持逗号、空格等分隔符，一次可输入多个</span>
        </div>
      </div>

      <el-row :gutter="16" class="task-create-c7__param-row">
        <el-col :xs="24" :md="12">
          <div class="sub-card task-create-c7__param-card">
            <div class="task-create-c7__config-title">参数 2</div>
            <el-input v-model="param2" type="textarea" :rows="3" placeholder='["v1", "v2"]' />
            <div class="panel-note task-create-c7__note">JSON 数组格式，可选。</div>
          </div>
        </el-col>
        <el-col :xs="24" :md="12">
          <div class="sub-card task-create-c7__param-card">
            <div class="task-create-c7__config-title">参数 3</div>
            <el-input v-model="param3" type="textarea" :rows="3" placeholder='["v1", "v2"]' />
            <div class="panel-note task-create-c7__note">JSON 数组格式，可选。</div>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <el-card v-if="combinationCount > 0" shadow="never" class="page-section">
      <div class="info-banner task-create-c7__summary">
        <span>
          <el-tag type="primary">{{ combinationCount }}</el-tag> 个参数组合将被执行
        </span>
        <el-button link type="primary" @click="previewVisible = true">预览组合</el-button>
      </div>
    </el-card>

    </el-form>

    <el-card shadow="never">
      <div class="action-bar">
        <el-button @click="clearSaved">清除数据</el-button>
        <el-button @click="openSaveTemplate">保存为模板</el-button>
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

    <el-dialog
      v-model="previewVisible"
      title="参数组合预览"
      width="480px"
      :fullscreen="isMobile"
    >
      <div class="task-create-c7__preview">
        <div v-for="(code, idx) in previewCombinations" :key="idx" class="task-create-c7__preview-item">
          <strong>组合 {{ idx + 1 }}:</strong>
          <span class="panel-note">{{ code }}</span>
        </div>
        <div v-if="previewTotal > previewCombinations.length" class="panel-note">
          ... 还有 {{ previewTotal - previewCombinations.length }} 个组合
        </div>
      </div>
      <template #footer>
        <el-button @click="previewVisible = false">关闭</el-button>
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
import { getEnums } from '@/api/meta'
import { useResponsive } from '@/composables/useResponsive'
import { defaultDateRange, formatDate } from '@/utils/tradingDate'

const route = useRoute()
const router = useRouter()
const { isMobile } = useResponsive()

// C7 版本差异配置（对齐静态页 templates/google_sheet_c7/create.html 的 window.__CTASK_CONFIG）
const TASK_TYPE = 'google_sheet_C7'
const TEMPLATE_TASK_TYPE = 'google_sheet_c7'
const KLINE_DATA_SOURCE_DEFAULT = 'akshare'
const DEFAULT_MODEL_VERSION = 'c7_0_2'
const RANDOM_TOKEN = '__random__'
const LS_KEY = 'vue_google_sheet_c7_form_data'

const pageTitle = ref('创建新任务 (C7)')
const sheetOptions = ref([])
const tokens = ref([])
const randomTokenValue = ref(RANDOM_TOKEN)
const marketOptions = ref([])
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
const previewVisible = ref(false)

const form = reactive({
  name: '',
  description: '',
  token_type: 'file',
  token_id: RANDOM_TOKEN,
  token_file: '',
  token_json: '',
  proxy_url: '',
  kline_source: 'auto',
  count_mode: 'total',
  price_mode: 'sp_price',
  random_price_range: 'high_low',
  random_group_count: 1,
  market_type: 'cn',
  kline_adjustment: 'forward',
  kline_data_source: KLINE_DATA_SOURCE_DEFAULT,
  start_date: '',
  end_date: ''
})

function emptySheetConfig() {
  return {
    spreadsheet_id: '',
    title: '',
    sheet_name: '',
    c7_model_version: DEFAULT_MODEL_VERSION,
    versionManual: false,
    worksheets: []
  }
}

const sheetConfigs = ref([emptySheetConfig()])
const templateForm = reactive({ name: '', description: '' })

// 近年排除选项：0.5 必须用 parseFloat 保留（对应静态版 exclude_year_half）
const recentYearOptions = [
  { value: 0.5, label: '近半年' },
  ...Array.from({ length: 10 }, (_, i) => ({ value: i + 1, label: `近${i + 1}年` }))
]

const isCustomKline = computed(() => form.kline_source === 'custom')
const dateRangeEnabled = computed(() => !isCustomKline.value && form.count_mode === 'n_plus_1')
const recentYearsEnabled = computed(() => !isCustomKline.value && dateRangeRecent.value)

// 已配置（选了 spreadsheet）的 Sheet 的 C7 模型版本集合
const configuredModelVersions = computed(() => {
  const versions = new Set()
  sheetConfigs.value.forEach((sheet) => {
    if (extractSpreadsheetId(sheet.spreadsheet_id || '') && sheet.c7_model_version) {
      versions.add(sheet.c7_model_version)
    }
  })
  return versions
})

// 全部已配置 Sheet 版本一致时返回该版本，用于禁用其它版本选项
const activeModelVersion = computed(() =>
  configuredModelVersions.value.size === 1 ? Array.from(configuredModelVersions.value)[0] : ''
)

// 任一 Sheet 为 C7.0.3 时强制 OHLC 价格（对齐静态版 enforceC7PriceMode）
const forceOhlcPrice = computed(() => configuredModelVersions.value.has('c7_0_3'))
const priceModeDisabled = computed(() => isCustomKline.value || forceOhlcPrice.value)
const showRandomOptions = computed(
  () => form.price_mode === 'random_price' && !isCustomKline.value && !forceOhlcPrice.value
)

const combinationCount = computed(() => {
  // 组合方式：第一组表格 * 参数1 * 参数2 * 参数3（随机价时再乘随机组数）
  const firstId = extractSpreadsheetId(sheetConfigs.value[0]?.spreadsheet_id || '')
  if (!firstId || !productCodes.value.length) return 0
  const param2Arr = parseJsonArrayStrict(param2.value)
  const param3Arr = parseJsonArrayStrict(param3.value)
  const len2 = (Array.isArray(param2Arr) ? param2Arr.length : 0) || 1
  const len3 = (Array.isArray(param3Arr) ? param3Arr.length : 0) || 1
  const randomGroups = form.price_mode === 'random_price'
    ? Math.max(1, parseInt(form.random_group_count || 1, 10) || 1)
    : 1
  return productCodes.value.length * len2 * len3 * randomGroups
})

const previewCombinations = computed(() => productCodes.value.slice(0, 20))
const previewTotal = computed(() => productCodes.value.length)

// 静态版 utils.js 同名函数：解析失败返回 null（供提交校验），空串返回 []
function parseJsonArrayStrict(text) {
  try {
    if (!String(text || '').trim()) return []
    return JSON.parse(text)
  } catch {
    return null
  }
}

function extractSpreadsheetId(input) {
  if (!input) return ''
  const match = String(input).match(/\/spreadsheets\/d\/([a-zA-Z0-9-_]+)/)
  return match ? match[1] : String(input).trim()
}

function versionOptionDisabled(value) {
  return Boolean(activeModelVersion.value && activeModelVersion.value !== value)
}

// ── 基础数据加载 ──

async function loadSheetOptions() {
  try {
    const res = await getGoogleSheets({ only_available: 1, table_type: 'c7' })
    sheetOptions.value = res.items || []
    // 模板/重启回填的 spreadsheet 可能不在可用列表中，补一个“当前配置”选项
    sheetConfigs.value.forEach((sheet) => ensureSheetOption(sheet.spreadsheet_id))
  } catch (err) {
    ElMessage.error(`加载 Google Sheet 失败：${err?.message || '未知错误'}`)
  }
}

// 回填的 spreadsheet 不在列表时补一个“当前配置 (id)”选项（对齐静态版行为）
function ensureSheetOption(spreadsheetId) {
  const id = extractSpreadsheetId(spreadsheetId || '')
  if (!id) return
  if (!sheetOptions.value.some((s) => s.spreadsheet_id === id)) {
    sheetOptions.value.push({ spreadsheet_id: id, name: '当前配置' })
  }
}

async function loadTokens() {
  try {
    const res = await getTokens({ task_type: 'google_sheet' })
    tokens.value = res.tokens || []
    if (res.random_value) randomTokenValue.value = res.random_value
  } catch {}
}

async function loadTemplates() {
  try {
    // 后端按 config.task_type 精确匹配，必须传小写 google_sheet_c7
    const res = await getTemplates({ task_type: TEMPLATE_TASK_TYPE })
    templates.value = res.templates || []
  } catch {}
}

async function loadMarketOptions() {
  try {
    const res = await getEnums()
    marketOptions.value = res?.stock_markets || []
  } catch {}
}

// ── Token 选择与同步（对齐静态版 form-state 的 syncSelectedTokenMeta / applyPendingTokenSelection）──

function syncTokenFile() {
  if (form.token_type !== 'file') {
    form.token_file = ''
    return
  }
  const selected = tokens.value.find((t) => String(t.id) === String(form.token_id))
  form.token_file = selected ? selected.token_file || '' : ''
}

watch(() => [form.token_type, form.token_id], syncTokenFile)

function resolveTokenSelection(selection) {
  if (!selection) return
  const { token_id, token_file, token_selection_mode } = selection
  const validValues = new Set([randomTokenValue.value, ...tokens.value.map((t) => String(t.id))])
  let matched = ''
  if (token_id && validValues.has(String(token_id))) {
    matched = String(token_id)
  } else if (token_file) {
    const matchedToken = tokens.value.find((t) => t.token_file === token_file)
    if (matchedToken) matched = String(matchedToken.id)
  }
  if (!matched && token_selection_mode === randomTokenValue.value) {
    matched = randomTokenValue.value
  }
  if (matched) form.token_id = matched
  syncTokenFile()
}

async function doImportToken() {
  if (!tokenImportPath.value.trim()) {
    ElMessage.warning('请输入 Token 文件路径')
    return
  }

  try {
    const res = await apiImportToken({ token_file: tokenImportPath.value.trim() })
    ElMessage.success('Token 导入成功')
    tokenImportPath.value = ''
    await loadTokens()
    if (res.token?.id) form.token_id = String(res.token.id)
  } catch (err) {
    ElMessage.error(`导入 Token 失败: ${err?.message || '未知错误'}`)
  }
}

// ── Sheet 配置块操作 ──

function addSheet() {
  sheetConfigs.value.push(emptySheetConfig())
}

function removeSheet(idx) {
  if (sheetConfigs.value.length <= 1) {
    ElMessage.info('至少保留一组表格配置')
    return
  }
  sheetConfigs.value.splice(idx, 1)
}

function onSheetChange(idx) {
  const sheet = sheetConfigs.value[idx]
  // 重新选择表格后版本恢复自动识别
  sheet.versionManual = false
  syncModelVersionControls()
  loadWorksheetsForSheet(idx, false)
}

function onModelVersionChange(idx) {
  const sheet = sheetConfigs.value[idx]
  sheet.versionManual = true
  ensureC7ModelVersionConsistency(idx, false)
}

// 未选表格的配置块跟随全局唯一已配置版本（对齐静态版 updateC7ModelVersionControls 的赋值部分）
function syncModelVersionControls() {
  const active = activeModelVersion.value
  if (!active) return
  sheetConfigs.value.forEach((sheet) => {
    if (!extractSpreadsheetId(sheet.spreadsheet_id || '') && sheet.c7_model_version !== active) {
      sheet.c7_model_version = active
    }
  })
}

// C7.0.2 与 C7.0.3 不能同时配置；冲突时回滚变更块（对齐静态版 ensureC7ModelVersionConsistency）
function ensureC7ModelVersionConsistency(changedIdx, clearChangedSheet = false) {
  const others = new Set(
    sheetConfigs.value
      .filter((s, i) => i !== changedIdx && extractSpreadsheetId(s.spreadsheet_id || '') && s.c7_model_version)
      .map((s) => s.c7_model_version)
  )
  const sheet = sheetConfigs.value[changedIdx]
  if (!sheet) return true

  if (others.size === 1 && !others.has(sheet.c7_model_version)) {
    const active = Array.from(others)[0]
    if (clearChangedSheet) {
      sheet.spreadsheet_id = ''
      sheet.title = ''
      sheet.sheet_name = ''
      sheet.worksheets = []
    }
    sheet.c7_model_version = active
    sheet.versionManual = true
    ElMessage.error('C7.0.2 与 C7.0.3 不能同时配置，请选择相同版本的 Google Sheet')
    return false
  }

  syncModelVersionControls()
  return true
}

// 提交前校验 sheets 集合版本一致性（对齐静态版 validateC7ModelVersionSet）
function validateC7ModelVersionSet(sheets) {
  const versions = new Set(
    sheets.map((sheet) => sheet.c7_model_version || DEFAULT_MODEL_VERSION).filter(Boolean)
  )
  if (versions.size <= 1) return true
  ElMessage.error('C7.0.2 与 C7.0.3 不能同时添加到 Sheet 配置')
  return false
}

async function loadWorksheetsForSheet(idx, isManualRefresh = false) {
  const sheet = sheetConfigs.value[idx]
  if (!sheet) return
  const spreadsheetId = extractSpreadsheetId(sheet.spreadsheet_id || '')
  if (!spreadsheetId) {
    sheet.sheet_name = ''
    return
  }

  try {
    const res = await getWorksheets({
      spreadsheet_id: spreadsheetId,
      token_id: form.token_type === 'file' ? form.token_id : undefined,
      token_file: form.token_type === 'file' ? form.token_file : undefined,
      proxy_url: form.proxy_url || undefined
    })
    if (!Array.isArray(res.worksheets)) {
      throw new Error(res.message || '获取工作表列表失败')
    }

    const sheetTitle = typeof res.title === 'string' ? res.title.trim() : ''
    if (sheetTitle) sheet.title = sheetTitle
    // 版本未被手动指定时按表标题自动识别
    if (!sheet.versionManual) {
      sheet.c7_model_version = sheetTitle.startsWith('C7.0.3') ? 'c7_0_3' : 'c7_0_2'
    }
    sheet.worksheets = res.worksheets
    sheet.sheet_name = res.worksheets.length ? res.worksheets[0] || '' : ''

    if (sheet.versionManual) {
      syncModelVersionControls()
    } else {
      ensureC7ModelVersionConsistency(idx, true)
    }
    ElMessage.success(isManualRefresh ? '表标题已刷新' : '表标题已自动加载')
  } catch (err) {
    console.error('获取工作表列表失败:', err)
    sheet.sheet_name = ''
    ElMessage.error('获取工作表列表失败: ' + (err?.message || '未知错误'))
  }
}

// ── 产品代码 chips ──

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
  ElMessage.info(`已移除产品代码 ${code}`)
}

// ── 日期默认值与范围模式 ──

function initDefaultDates() {
  if (form.start_date || form.end_date) return
  const range = defaultDateRange(5)
  form.end_date = formatDate(range.end)
  form.start_date = formatDate(range.start)
}

// 对齐静态版 applyDateRangeModes：字符串包装为数组，空则默认 ['full']
function applyDateRangeModes(raw) {
  let modes = []
  if (Array.isArray(raw)) modes = raw
  else if (typeof raw === 'string' && raw) modes = [raw]
  if (!modes.length) modes = ['full']
  dateRangeFull.value = modes.includes('full')
  dateRangeRecent.value = modes.includes('recent')
}

// 纯函数版 getSelectedDateRangeModes：未勾选时按静态版语义回落 ['full']
function selectedDateRangeModes() {
  if (isCustomKline.value) return []
  const modes = []
  if (dateRangeFull.value) modes.push('full')
  if (dateRangeRecent.value) modes.push('recent')
  return modes.length ? modes : ['full']
}

// 对齐静态版 getExcludedRecentYears：仅勾选“近年”时生效
function excludedRecentYears() {
  if (isCustomKline.value) return []
  if (!dateRangeRecent.value) return []
  return excludeYears.value.map((v) => parseFloat(v)).filter((v) => !Number.isNaN(v))
}

// ── 自定义K线 / 价格模式联动（对齐静态版 updateCustomKlineModeAvailability / enforceC7PriceMode）──

watch(
  () => [form.kline_source, form.count_mode, dateRangeRecent.value],
  () => {
    const custom = isCustomKline.value
    if (custom && form.count_mode !== 'total') form.count_mode = 'total'
    if (custom) {
      if (form.market_type !== '') form.market_type = ''
    } else if (!form.market_type) {
      form.market_type = 'cn'
    }

    const enableDateRange = !custom && form.count_mode === 'n_plus_1'
    if (!enableDateRange) {
      if (dateRangeFull.value) dateRangeFull.value = false
      if (dateRangeRecent.value) dateRangeRecent.value = false
    }
    if (custom || !dateRangeRecent.value) {
      if (excludeYears.value.length) excludeYears.value = []
    }
  },
  { immediate: true }
)

watch(
  forceOhlcPrice,
  (forced) => {
    if (forced) {
      if (form.price_mode !== 'ohlc_price') form.price_mode = 'ohlc_price'
    } else if (form.price_mode === 'ohlc_price') {
      form.price_mode = 'vwap_price'
    }
  },
  { immediate: true }
)

// ── 模板 / 重启 / 本地草稿回填 ──

// 对齐静态版 normalizeC4Config：旧结构（顶层 spreadsheet_id）转 sheets 数组
function normalizeC7Config(raw) {
  if (!raw || typeof raw !== 'object') return {}

  if (Array.isArray(raw.sheets) && raw.sheets.length > 0) {
    return { ...raw, kline_source: raw.kline_source || 'auto' }
  }

  const sheets = []
  if (raw.spreadsheet_id) {
    sheets.push({
      spreadsheet_id: raw.spreadsheet_id,
      sheet_name: raw.sheet_name || '',
      title: raw.title || ''
    })
  }

  return {
    kline_source: raw.kline_source || 'auto',
    kline_data_source: raw.kline_data_source || KLINE_DATA_SOURCE_DEFAULT,
    count_mode: raw.count_mode || 'total',
    price_mode: raw.price_mode || 'vwap_price',
    random_price_range: raw.random_price_range || 'high_low',
    random_group_count: raw.random_group_count || 1,
    start_date: raw.start_date || null,
    end_date: raw.end_date || null,
    market_type: raw.market_type || 'cn',
    kline_adjustment: raw.kline_adjustment || 'forward',
    token_type: raw.token_type || 'file',
    token_id: raw.token_id || '',
    token_file: raw.token_file || 'data/token.json',
    token_json: raw.token_json || '',
    proxy_url: raw.proxy_url || null,
    parameters: Array.isArray(raw.parameters) ? raw.parameters : [[]],
    sheets
  }
}

function applySheets(sheets) {
  if (!Array.isArray(sheets) || !sheets.length) return

  sheetConfigs.value = sheets.map((cfg) => ({
    spreadsheet_id: cfg.spreadsheet_id || '',
    title: cfg.title || '',
    sheet_name: cfg.sheet_name || '',
    c7_model_version: cfg.c7_model_version || DEFAULT_MODEL_VERSION,
    versionManual: Boolean(cfg.c7_model_version),
    worksheets: []
  }))

  sheetConfigs.value.forEach((sheet) => ensureSheetOption(sheet.spreadsheet_id))
  // 对齐静态版：回填后逐组自动拉取表标题/工作表（失败时保留回填值）
  sheetConfigs.value.forEach((sheet, idx) => {
    if (sheet.spreadsheet_id) loadWorksheetsForSheet(idx, false)
  })
}

function applyConfig(rawConfig, options = {}) {
  const config = normalizeC7Config(rawConfig)

  if (options.name) form.name = options.name

  applySheets(config.sheets)

  if (config.token_type) form.token_type = config.token_type
  resolveTokenSelection({
    token_id: config.token_id || '',
    token_file: config.token_file || '',
    token_selection_mode: config.token_selection_mode || ''
  })
  if (config.token_file) form.token_file = config.token_file
  if (config.token_json) form.token_json = config.token_json
  if (config.proxy_url) form.proxy_url = config.proxy_url

  if (config.kline_source) form.kline_source = config.kline_source
  if (config.count_mode) form.count_mode = config.count_mode
  form.price_mode = config.price_mode || 'vwap_price'
  form.random_price_range = config.random_price_range || 'high_low'
  form.random_group_count = Number(config.random_group_count) || 1
  if (config.market_type) form.market_type = config.market_type
  if (config.kline_adjustment) form.kline_adjustment = config.kline_adjustment
  if (config.kline_data_source) form.kline_data_source = config.kline_data_source
  if (config.start_date) form.start_date = config.start_date
  if (config.end_date) form.end_date = config.end_date
  if (config.date_range_mode !== undefined) applyDateRangeModes(config.date_range_mode)
  if (Array.isArray(config.exclude_recent_years)) excludeYears.value = config.exclude_recent_years

  if (Array.isArray(config.parameters)) {
    if (Array.isArray(config.parameters[0])) productCodes.value = config.parameters[0]
    if (Array.isArray(config.parameters[1])) param2.value = JSON.stringify(config.parameters[1])
    if (Array.isArray(config.parameters[2])) param3.value = JSON.stringify(config.parameters[2])
  }

  // 收尾重新执行价格模式强制（对齐静态版 applyConfigToForm 末尾的 updateCustomKlineModeAvailability）
  if (forceOhlcPrice.value) {
    form.price_mode = 'ohlc_price'
  } else if (form.price_mode === 'ohlc_price') {
    form.price_mode = 'vwap_price'
  }
}

async function applyTemplate(id) {
  if (!id) return

  try {
    const tpl = await getTemplate(id)
    const config = typeof tpl.config === 'string' ? JSON.parse(tpl.config) : tpl.config || {}
    applyConfig(config, { mode: 'template', name: tpl.name })
    ElMessage.success('模板配置已加载')
  } catch (err) {
    console.error('加载模板详情失败:', err)
    ElMessage.error('加载模板失败')
  }
}

async function loadRestartTask(taskId) {
  try {
    const res = await getTask(taskId)
    const task = res.task || res
    if (!task?.config) {
      ElMessage.error('加载原任务配置失败：config为空')
      return
    }
    pageTitle.value = '重启任务 (C7)'
    applyConfig(task.config, { mode: 'restart', name: task.name ? `${task.name} (重启)` : '' })
    ElMessage.info('已加载原任务配置')
  } catch (err) {
    console.error('加载原任务失败:', err)
    ElMessage.error('加载原任务失败')
  }
}

// ── localStorage 草稿 ──

function saveFormData() {
  try {
    localStorage.setItem(
      LS_KEY,
      JSON.stringify({
        name: form.name,
        description: form.description,
        sheetConfigs: sheetConfigs.value
          .map((sheet) => ({
            spreadsheet_id: extractSpreadsheetId(sheet.spreadsheet_id || ''),
            title: sheet.title,
            sheet_name: sheet.sheet_name,
            c7_model_version: sheet.c7_model_version || DEFAULT_MODEL_VERSION
          }))
          .filter((sheet) => sheet.spreadsheet_id),
        token_type: form.token_type,
        token_id: form.token_id,
        token_file: form.token_file,
        token_json: form.token_json,
        proxy_url: form.proxy_url,
        kline_source: form.kline_source,
        count_mode: form.count_mode,
        price_mode: form.price_mode,
        random_price_range: form.random_price_range,
        random_group_count: parseInt(form.random_group_count || 1, 10),
        market_type: form.market_type,
        kline_adjustment: form.kline_adjustment,
        kline_data_source: form.kline_data_source,
        date_range_mode: selectedDateRangeModes(),
        exclude_recent_years: excludedRecentYears(),
        productCodes: productCodes.value,
        param2: param2.value,
        param3: param3.value
      })
    )
  } catch (e) {
    console.warn('无法保存表单数据到localStorage:', e)
  }
}

function loadSavedFormData() {
  try {
    const saved = localStorage.getItem(LS_KEY)
    if (!saved) return

    const data = JSON.parse(saved)

    if (data.name) form.name = data.name
    if (data.description) form.description = data.description
    if (Array.isArray(data.sheetConfigs) && data.sheetConfigs.length) applySheets(data.sheetConfigs)
    if (data.token_type) form.token_type = data.token_type
    if (data.token_id) resolveTokenSelection({ token_id: data.token_id, token_file: data.token_file || '' })
    if (data.token_file) form.token_file = data.token_file
    if (data.token_json) form.token_json = data.token_json
    if (data.proxy_url) form.proxy_url = data.proxy_url
    if (data.market_type) form.market_type = data.market_type
    if (data.kline_source) form.kline_source = data.kline_source
    if (data.kline_adjustment) form.kline_adjustment = data.kline_adjustment
    if (data.kline_data_source) form.kline_data_source = data.kline_data_source
    if (data.count_mode) form.count_mode = data.count_mode
    if (data.price_mode) form.price_mode = data.price_mode
    if (data.random_price_range) form.random_price_range = data.random_price_range
    if (data.random_group_count) form.random_group_count = Number(data.random_group_count) || 1
    if (data.date_range_mode !== undefined) applyDateRangeModes(data.date_range_mode)
    if (Array.isArray(data.exclude_recent_years)) excludeYears.value = data.exclude_recent_years
    if (Array.isArray(data.productCodes)) productCodes.value = data.productCodes
    if (data.param2) param2.value = data.param2
    if (data.param3) param3.value = data.param3

    ElMessage.info('表单数据已恢复')
  } catch (e) {
    console.warn('无法从localStorage加载表单数据:', e)
  }
}

function clearSaved() {
  try {
    localStorage.removeItem(LS_KEY)
  } catch {}
  Object.assign(form, {
    name: '',
    description: '',
    token_type: 'file',
    token_id: randomTokenValue.value,
    token_file: '',
    token_json: '',
    proxy_url: '',
    kline_source: 'auto',
    count_mode: 'total',
    price_mode: 'sp_price',
    random_price_range: 'high_low',
    random_group_count: 1,
    market_type: 'cn',
    kline_adjustment: 'forward',
    kline_data_source: KLINE_DATA_SOURCE_DEFAULT,
    start_date: '',
    end_date: ''
  })
  sheetConfigs.value = [emptySheetConfig()]
  productCodes.value = []
  dateRangeFull.value = false
  dateRangeRecent.value = false
  excludeYears.value = []
  param2.value = ''
  param3.value = ''
  selectedTemplate.value = ''
  ElMessage.success('已清除 c7 表单缓存')
}

// ── 提交 ──

// 构造任务/模板 config（对齐静态版 submitTask 的 taskConfig 与 getCurrentConfig，逐字段透传）
function buildCurrentConfig({ forTemplate }) {
  const custom = isCustomKline.value
  let priceMode = custom ? null : (form.price_mode || 'vwap_price')
  const randomGroupCount = parseInt(form.random_group_count || 1, 10)

  if (priceMode === 'random_price' && (!Number.isInteger(randomGroupCount) || randomGroupCount < 1)) {
    ElMessage.error('随机组数必须是正整数')
    return null
  }

  if (forTemplate && !extractSpreadsheetId(sheetConfigs.value[0]?.spreadsheet_id || '')) {
    ElMessage.error('请选择 Google Sheet')
    return null
  }

  if (form.token_type === 'file' && !form.token_id) {
    ElMessage.error('请选择Token')
    return null
  }
  if (form.token_type === 'json' && !form.token_json) {
    ElMessage.error('请输入Token JSON字符串')
    return null
  }

  // 参数1 = 产品代码 chips（等价静态版隐藏 param1）；参数2/3 为 JSON 数组文本
  const param1 = Array.isArray(productCodes.value) ? productCodes.value : []
  const parsedParam2 = parseJsonArrayStrict(param2.value)
  const parsedParam3 = parseJsonArrayStrict(param3.value)
  if (parsedParam2 === null || parsedParam3 === null) {
    ElMessage.error('参数格式错误，请检查 JSON 数组格式')
    return null
  }

  // 收集所有表格配置（仅保留已选 spreadsheet 的组）
  const sheets = []
  sheetConfigs.value.forEach((sheet) => {
    const sid = extractSpreadsheetId(sheet.spreadsheet_id || '')
    if (!sid) return
    const sheetConfig = {
      spreadsheet_id: sid,
      title: (sheet.title || '').trim(),
      c7_model_version: sheet.c7_model_version || DEFAULT_MODEL_VERSION
    }
    const sheetName = (sheet.sheet_name || '').trim()
    if (sheetName) sheetConfig.sheet_name = sheetName
    sheets.push(sheetConfig)
  })

  if (!validateC7ModelVersionSet(sheets)) return null
  if (!custom && sheets.some((sheet) => sheet.c7_model_version === 'c7_0_3')) {
    priceMode = 'ohlc_price'
  }

  // 参数列表：只加入非空数组（模板路径允许空的参数1，与静态版 getCurrentConfig 一致）
  const parameters = []
  if (forTemplate || param1.length) parameters.push(param1)
  if (parsedParam2.length) parameters.push(parsedParam2)
  if (parsedParam3.length) parameters.push(parsedParam3)

  return {
    ...(forTemplate ? { task_type: TEMPLATE_TASK_TYPE } : {}),
    token_type: form.token_type,
    token_id: form.token_type === 'file' ? form.token_id : null,
    token_file: form.token_file,
    token_json: form.token_json,
    proxy_url: form.proxy_url || null,
    kline_source: form.kline_source || 'auto',
    count_mode: custom ? 'total' : (form.count_mode || 'total'),
    price_mode: priceMode,
    random_price_range: priceMode === 'random_price' ? (form.random_price_range || 'high_low') : null,
    random_group_count: priceMode === 'random_price' ? randomGroupCount : 1,
    market_type: custom ? null : (form.market_type || 'cn'),
    kline_adjustment: custom ? null : (form.kline_adjustment || 'forward'),
    kline_data_source: form.kline_data_source || KLINE_DATA_SOURCE_DEFAULT,
    date_range_mode: selectedDateRangeModes(),
    exclude_recent_years: custom ? [] : excludedRecentYears(),
    start_date: custom ? null : (form.start_date || null),
    end_date: custom ? null : (form.end_date || null),
    parameters,
    sheets
  }
}

async function submit() {
  const combination = combinationCount.value
  if (!combination) {
    ElMessage.error('请至少输入一个参数')
    return
  }

  const config = buildCurrentConfig({ forTemplate: false })
  if (!config) return

  submitting.value = true
  try {
    const res = await createTask({
      name: form.name.trim() || `Google Sheet 任务 - ${new Date().toLocaleString()}`,
      description: form.description.trim() || `批量执行 ${combination} 个参数组合`,
      task_type: TASK_TYPE,
      config
    })
    ElMessage.success('任务创建成功，正在跳转到详情页面...')
    clearSaved()
    const taskId = res.task_id
    setTimeout(() => router.push(`/task/${taskId}`), 1000)
  } catch (err) {
    ElMessage.error('创建任务失败: ' + (err?.message || '未知错误'))
  } finally {
    submitting.value = false
  }
}

// ── 保存为模板 ──

function openSaveTemplate() {
  // 对齐静态版 saveAsTemplate：用任务名预填模板名
  if (form.name.trim() && !templateForm.name) {
    templateForm.name = `${form.name.trim()} 模板`
  }
  saveTemplateVisible.value = true
}

async function doSaveTemplate() {
  if (!templateForm.name) {
    ElMessage.warning('请输入模板名称')
    return
  }

  const config = buildCurrentConfig({ forTemplate: true })
  if (!config) return

  savingTemplate.value = true
  try {
    await createTemplate({
      name: templateForm.name,
      description: templateForm.description,
      config
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
  await Promise.all([loadSheetOptions(), loadTokens(), loadTemplates(), loadMarketOptions()])
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

.task-create-c7__sheet-card {
  margin-bottom: 12px;
}

.task-create-c7__sheet-head {
  margin-bottom: 8px;
}

.task-create-c7__sheet-title,
.task-create-c7__config-title {
  color: var(--app-text);
  font-size: 13px;
  font-weight: 700;
}

.task-create-c7__collapse {
  margin-top: 8px;
}

.task-create-c7__field-gap {
  margin-top: 8px;
}

.task-create-c7__config-card,
.task-create-c7__param-card {
  height: 100%;
}

.task-create-c7__note {
  margin-top: 4px;
}

.task-create-c7__range-card,
.task-create-c7__product-block,
.task-create-c7__param-row {
  margin-top: 16px;
}

.task-create-c7__product-head {
  margin-bottom: 8px;
}

.task-create-c7__exclude-wrap {
  margin-top: 8px;
}

.task-create-c7__exclude-wrap .task-create-c7__config-title {
  margin-bottom: 8px;
}

.task-create-c7__tag-wall {
  margin-top: 8px;
}

.task-create-c7__summary {
  justify-content: center;
  gap: 12px;
}

.task-create-c7__preview-item {
  padding: 8px;
  margin-bottom: 8px;
  border: 1px solid var(--app-border);
  border-radius: 6px;
}
</style>
