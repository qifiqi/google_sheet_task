<template>
  <div class="app-page backtest-create-page">
    <div class="page-toolbar">
      <div class="page-toolbar__meta">
        <div class="page-toolbar__eyebrow">Backtest Builder</div>
        <h2 class="page-title">创建数据回测任务</h2>
        <p class="page-description">从 Google Sheet 识别参数结构，补充股票与年份范围，直接生成回测训练任务。</p>
      </div>
      <div class="page-toolbar__actions">
        <el-button class="page-back-button" @click="$router.push('/backtest/list')">返回列表</el-button>
      </div>
    </div>

    <el-card shadow="never" class="page-section">
      <div class="section-heading">
        <h3 class="section-title section-title--muted">基础配置</h3>
      </div>

      <el-row :gutter="16">
        <el-col :xs="24" :sm="10">
          <el-form-item label="Google Sheet URL">
            <div class="control-row control-row--stretch">
              <el-input
                v-model="sheetUrl"
                placeholder="粘贴完整的 Google Sheet 链接"
              />
              <el-button type="primary" :loading="analyzing" @click="analyze">智能识别</el-button>
            </div>
          </el-form-item>
        </el-col>

        <el-col :xs="24" :sm="6">
          <el-form-item label="股票代码">
            <div class="backtest-create-page__search-wrap">
              <el-input
                v-model="stockCode"
                placeholder="例如 AAPL 或 601318"
                @input="onStockInput"
                @blur="hideSearch"
              />
              <div v-if="stockSearchResults.length" class="backtest-create-page__search-panel">
                <div
                  v-for="stock in stockSearchResults"
                  :key="stock.code"
                  class="backtest-create-page__search-item"
                  @mousedown.prevent="selectStock(stock)"
                >
                  <div class="backtest-create-page__search-code">{{ stock.code }}</div>
                  <div class="panel-note">{{ stock.name }} | {{ stock.market }}</div>
                </div>
              </div>
            </div>
          </el-form-item>
        </el-col>

        <el-col :xs="24" :sm="4">
          <el-form-item label="市场">
            <el-radio-group v-model="form.market_type">
              <el-radio-button value="cn">A股</el-radio-button>
              <el-radio-button value="us">美股</el-radio-button>
            </el-radio-group>
          </el-form-item>
        </el-col>
        <el-col :xs="24" :sm="4">
          <el-form-item label="K线复权">
            <el-select v-model="form.kline_adjustment" class="full-width">
              <el-option value="forward" label="前复权" />
              <el-option value="back" label="后复权" />
              <el-option value="none" label="不复权" />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>

      <el-collapse v-model="configOpen" class="backtest-create-page__collapse">
        <el-collapse-item title="任务配置与识别结果" name="config">
          <el-row :gutter="16">
            <el-col :xs="24" :sm="8">
              <el-form-item label="任务名称">
                <el-input v-model="form.task_name" placeholder="留空按默认规则自动生成" />
              </el-form-item>
            </el-col>
            <el-col :xs="24" :sm="8">
              <el-form-item label="回测 Token">
                <el-select v-model="form.token_id" class="full-width" placeholder="选择 Token">
                  <el-option
                    v-for="token in tokens"
                    :key="token.id"
                    :value="String(token.id)"
                    :label="`${token.name} | 占用 ${token.current_in_use_count || 0}`"
                    :disabled="!token.is_available"
                  />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :xs="24" :sm="8">
              <el-form-item label="手续费">
                <el-input v-model="form.commission" placeholder="例如 0.0350%" />
              </el-form-item>
            </el-col>
          </el-row>

          <div class="sub-card backtest-create-page__year-card">
            <div class="section-heading backtest-create-page__year-head">
              <div>
                <div class="backtest-create-page__card-title">年份范围</div>
                <div class="panel-note">可同时选择近年范围和整年范围，系统会带入任务配置。</div>
              </div>
              <div class="control-row">
                <el-checkbox v-model="useRecentYears" label="选择近年" />
                <el-checkbox v-model="useFullYears" label="选择整年" />
              </div>
            </div>

            <el-row :gutter="16">
              <el-col v-if="useRecentYears && recentYearOptions.length" :xs="24" :sm="12">
                <div class="backtest-create-page__option-title">近年范围</div>
                <div class="tag-wall">
                  <el-checkbox-group v-model="selectedRecentYears">
                    <el-checkbox v-for="year in recentYearOptions" :key="year" :label="year">
                      {{ year }}
                    </el-checkbox>
                  </el-checkbox-group>
                </div>
              </el-col>

              <el-col v-if="useFullYears && fullYearOptions.length" :xs="24" :sm="12">
                <div class="backtest-create-page__option-title">整年范围</div>
                <div class="tag-wall">
                  <el-checkbox-group v-model="selectedFullYears">
                    <el-checkbox v-for="year in fullYearOptions" :key="year" :label="year">
                      {{ year }}
                    </el-checkbox>
                  </el-checkbox-group>
                </div>
              </el-col>
            </el-row>
          </div>

          <div v-if="sheetInfo" class="info-banner backtest-create-page__sheet-banner">
            <span>
              <el-tag type="primary">{{ sheetInfo.model_version || 'C3' }}</el-tag>
              <strong>{{ sheetInfo.title }}</strong>
              <span class="panel-note">Sheet: {{ (sheetInfo.worksheets || []).join(', ') }}</span>
            </span>
          </div>
        </el-collapse-item>
      </el-collapse>
    </el-card>

    <el-card v-if="paramHeaders.length" shadow="never" class="page-section">
      <div class="section-heading">
        <div>
          <h3 class="section-title section-title--muted">参数配置清单</h3>
          <div class="panel-note">{{ excelImportStatus }}</div>
        </div>
        <div class="section-actions">
          <el-upload :show-file-list="false" accept=".xlsx,.xlsm" :before-upload="importExcelFile">
            <el-button size="small">从 Excel 导入参数</el-button>
          </el-upload>
          <el-button size="small" @click="addParamRow">添加一组</el-button>
          <el-button size="small" type="primary" :loading="submitting" @click="submit">提交创建</el-button>
        </div>
      </div>

      <el-table :data="paramRows" border>
        <el-table-column
          v-for="(header, index) in paramHeaders"
          :key="index"
          :label="header"
          min-width="120"
        >
          <template #default="{ $index }">
            <el-input v-model="paramRows[$index][index]" size="small" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="70">
          <template #default="{ $index }">
            <el-button link type="danger" size="small" @click="paramRows.splice($index, 1)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card v-else shadow="never" class="page-section">
      <div class="panel-note panel-note--center backtest-create-page__empty">
        请先输入 Google Sheet URL 并点击“智能识别”
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { importExcel, searchStocks } from '@/api/backtest'
import { getTokens } from '@/api/googleSheet'
import { createTask } from '@/api/task'

const router = useRouter()
const sheetUrl = ref('')
const stockCode = ref('')
const analyzing = ref(false)
const submitting = ref(false)
const tokens = ref([])
const stockSearchResults = ref([])
const sheetInfo = ref(null)
const paramHeaders = ref([])
const paramRows = ref([])
const excelImportStatus = ref('导入后会自动填充股票代码、年份和参数行。')
const configOpen = ref([])
const useRecentYears = ref(false)
const useFullYears = ref(true)
const recentYearOptions = ref([])
const fullYearOptions = ref([])
const selectedRecentYears = ref([])
const selectedFullYears = ref([])

const form = reactive({
  task_name: '',
  token_id: '',
  commission: '0.0350%',
  market_type: 'cn',
  kline_adjustment: 'forward'
})

let searchTimer = null

async function loadTokens() {
  try {
    const res = await getTokens()
    tokens.value = res.tokens || []
  } catch {}
}

function onStockInput() {
  clearTimeout(searchTimer)
  if (!stockCode.value.trim()) {
    stockSearchResults.value = []
    return
  }

  searchTimer = setTimeout(async () => {
    try {
      const res = await searchStocks({ q: stockCode.value.trim() })
      stockSearchResults.value = res.results || []
    } catch {
      stockSearchResults.value = []
    }
  }, 300)
}

function selectStock(stock) {
  stockCode.value = stock.code
  stockSearchResults.value = []
}

function hideSearch() {
  setTimeout(() => {
    stockSearchResults.value = []
  }, 200)
}

async function analyze() {
  if (!sheetUrl.value.trim()) {
    ElMessage.warning('请输入 Google Sheet URL')
    return
  }

  analyzing.value = true
  configOpen.value = ['config']
  try {
    const res = await importExcel({
      url: sheetUrl.value.trim(),
      stock_code: stockCode.value.trim(),
      market_type: form.market_type
    })
    sheetInfo.value = res
    paramHeaders.value = res.headers || []
    paramRows.value = (res.rows || []).map((row) => (Array.isArray(row) ? row : []))
    recentYearOptions.value = res.recent_years || []
    fullYearOptions.value = res.full_years || []
    selectedFullYears.value = (res.full_years || []).slice(0, 3)
    ElMessage.success('识别成功')
  } catch {
    ElMessage.error('识别失败，请检查 URL 是否正确')
  } finally {
    analyzing.value = false
  }
}

async function importExcelFile(file) {
  const formData = new FormData()
  formData.append('file', file)
  try {
    const res = await importExcel(formData)
    paramHeaders.value = res.headers || []
    paramRows.value = (res.rows || []).map((row) => (Array.isArray(row) ? row : []))
    excelImportStatus.value = `已导入 ${paramRows.value.length} 行参数`
    ElMessage.success('Excel 导入成功')
  } catch {
    ElMessage.error('Excel 导入失败')
  }
  return false
}

function addParamRow() {
  paramRows.value.push(paramHeaders.value.map(() => ''))
}

async function submit() {
  if (!stockCode.value.trim()) {
    ElMessage.error('请输入股票代码')
    return
  }

  if (!paramRows.value.length) {
    ElMessage.error('请至少添加一组参数')
    return
  }

  submitting.value = true
  try {
    const res = await createTask({
      name: form.task_name || `回测-${stockCode.value}-${new Date().toLocaleString()}`,
      task_type: 'backtest_training',
      config: {
        sheet_url: sheetUrl.value,
        stock_code: stockCode.value,
        market_type: form.market_type,
        kline_adjustment: form.kline_adjustment,
        token_id: form.token_id || null,
        commission: form.commission,
        recent_years: useRecentYears.value ? selectedRecentYears.value : [],
        full_years: useFullYears.value ? selectedFullYears.value : [],
        headers: paramHeaders.value,
        rows: paramRows.value,
        model_version: sheetInfo.value?.model_version || 'C3'
      }
    })
    ElMessage.success('任务创建成功')
    setTimeout(() => router.push(`/backtest/${res.task_id}`), 800)
  } catch {
    ElMessage.error('创建任务失败')
  } finally {
    submitting.value = false
  }
}

onMounted(() => loadTokens())
</script>

<style scoped>
.full-width {
  width: 100%;
}

.backtest-create-page__search-wrap {
  position: relative;
}

.backtest-create-page__search-panel {
  position: absolute;
  z-index: 20;
  width: 100%;
  max-height: 220px;
  overflow-y: auto;
  border: 1px solid var(--app-border);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.98);
  box-shadow: var(--app-shadow-soft);
}

.backtest-create-page__search-item {
  padding: 10px 12px;
  cursor: pointer;
  border-bottom: 1px solid rgba(30, 64, 175, 0.08);
}

.backtest-create-page__search-item:last-child {
  border-bottom: none;
}

.backtest-create-page__search-code,
.backtest-create-page__card-title,
.backtest-create-page__option-title {
  color: var(--app-text);
  font-size: 13px;
  font-weight: 700;
}

.backtest-create-page__collapse {
  margin-top: 8px;
}

.backtest-create-page__year-card {
  margin-top: 8px;
}

.backtest-create-page__year-head {
  margin-bottom: 8px;
}

.backtest-create-page__option-title {
  margin-bottom: 8px;
}

.backtest-create-page__sheet-banner {
  margin-top: 12px;
}

.backtest-create-page__sheet-banner :deep(.el-tag) {
  margin-right: 8px;
}

.backtest-create-page__empty {
  padding: 24px;
}
</style>
