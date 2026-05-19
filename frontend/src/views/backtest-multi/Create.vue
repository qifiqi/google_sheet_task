<template>
  <div class="app-page backtest-multi-create-page">
    <PageToolbar
      eyebrow="Multi-Product Builder"
      title="创建多产品回测任务"
      description="配置多个产品的参数和比例，生成多产品组合回测任务。"
    >
      <template #actions>
        <el-upload :show-file-list="false" accept=".xlsx,.xlsm" :before-upload="handleImportExcel">
          <el-button>从 Excel 导入</el-button>
        </el-upload>
        <el-button type="primary" :loading="submitting" @click="submit">提交创建</el-button>
        <el-button class="page-back-button" @click="$router.push('/backtest-multi/list')">返回列表</el-button>
      </template>
    </PageToolbar>

    <el-card shadow="never" class="page-section">
      <div class="section-heading">
        <h3 class="section-title section-title--muted">基础配置</h3>
      </div>
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
    </el-card>

    <!-- Product Cards -->
    <el-card
      v-for="(product, pIndex) in products"
      :key="pIndex"
      shadow="never"
      class="page-section backtest-multi-create-page__product-card"
    >
      <div class="section-heading">
        <div>
          <h3 class="section-title section-title--muted">产品 {{ pIndex + 1 }}</h3>
          <div class="panel-note">配置股票、市场、年份和参数</div>
        </div>
        <div class="section-actions">
          <el-button v-if="products.length > 1" size="small" type="danger" @click="removeProduct(pIndex)">
            移除产品
          </el-button>
        </div>
      </div>

      <el-row :gutter="16">
        <el-col :xs="24" :sm="8">
          <el-form-item label="股票代码">
            <div class="backtest-multi-create-page__search-wrap">
              <el-input
                v-model="product.stock_code"
                placeholder="例如 AAPL 或 601318"
                @input="onStockInput(pIndex)"
                @blur="hideSearch(pIndex)"
              />
              <div v-if="product.searchResults.length" class="backtest-multi-create-page__search-panel">
                <div
                  v-for="stock in product.searchResults"
                  :key="stock.code"
                  class="backtest-multi-create-page__search-item"
                  @mousedown.prevent="selectStock(pIndex, stock)"
                >
                  <div class="backtest-multi-create-page__search-code">{{ stock.code }}</div>
                  <div class="panel-note">{{ stock.name }} | {{ stock.market }}</div>
                </div>
              </div>
            </div>
          </el-form-item>
        </el-col>
        <el-col :xs="24" :sm="4">
          <el-form-item label="市场">
            <el-radio-group v-model="product.market_type">
              <el-radio-button value="cn">A股</el-radio-button>
              <el-radio-button value="us">美股</el-radio-button>
            </el-radio-group>
          </el-form-item>
        </el-col>
        <el-col :xs="24" :sm="6">
          <el-form-item label="年份">
            <el-select v-model="product.years" multiple class="full-width" placeholder="选择年份">
              <el-option v-for="y in yearOptions" :key="y" :value="y" :label="String(y)" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :xs="24" :sm="6">
          <el-form-item label="比例 (%)">
            <el-input-number v-model="product.ratio" :min="0" :max="100" :step="5" />
          </el-form-item>
        </el-col>
      </el-row>

      <!-- Parameter Table -->
      <div class="backtest-multi-create-page__param-section">
        <div class="section-heading">
          <div class="panel-note">参数表 (可粘贴 Tab 分隔数据)</div>
          <div class="section-actions">
            <el-button size="small" @click="addParamRow(pIndex)">添加行</el-button>
          </div>
        </div>
        <div class="backtest-multi-create-page__paste-area">
          <el-input
            v-model="product.pasteText"
            type="textarea"
            :rows="2"
            placeholder="粘贴 Tab 分隔的参数数据，自动解析为参数行"
            @change="parsePaste(pIndex)"
          />
        </div>
        <el-table v-if="product.paramRows.length" :data="product.paramRows" border size="small">
          <el-table-column
            v-for="(header, hIndex) in product.paramHeaders"
            :key="hIndex"
            :label="header"
            min-width="100"
          >
            <template #default="{ $index }">
              <el-input v-model="product.paramRows[$index][hIndex]" size="small" />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="60">
            <template #default="{ $index }">
              <el-button link type="danger" size="small" @click="product.paramRows.splice($index, 1)">删</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-card>

    <!-- Ratio Summary & Add Product -->
    <el-card shadow="never" class="page-section">
      <div class="section-heading">
        <h3 class="section-title section-title--muted">产品比例汇总</h3>
        <div class="section-actions">
          <el-button type="primary" size="small" @click="addProduct">添加产品</el-button>
        </div>
      </div>
      <div class="backtest-multi-create-page__ratio-bar">
        <el-tag
          v-for="(product, pIndex) in products"
          :key="pIndex"
          :type="ratioTotal === 100 ? 'success' : 'warning'"
          size="large"
          class="backtest-multi-create-page__ratio-pill"
        >
          产品{{ pIndex + 1 }}: {{ product.stock_code || '未设置' }} — {{ product.ratio }}%
        </el-tag>
        <el-tag :type="ratioTotal === 100 ? 'success' : 'danger'" size="large">
          合计: {{ ratioTotal }}%
        </el-tag>
      </div>
      <div v-if="ratioTotal !== 100" class="backtest-multi-create-page__ratio-warn">
        比例总和必须为 100%，当前为 {{ ratioTotal }}%
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { importExcel, searchStocks } from '@/api/backtestMulti'
import { getTokens } from '@/api/googleSheet'
import { createTask } from '@/api/task'
import PageToolbar from '@/components/PageToolbar.vue'
import { useResponsive } from '@/composables/useResponsive'

const router = useRouter()
useResponsive()

const submitting = ref(false)
const tokens = ref([])
const form = reactive({
  task_name: '',
  token_id: '',
  commission: '0.0350%'
})

const currentYear = new Date().getFullYear()
const yearOptions = Array.from({ length: 10 }, (_, i) => currentYear - i)

function createEmptyProduct() {
  return reactive({
    stock_code: '',
    market_type: 'cn',
    years: [currentYear],
    ratio: 0,
    paramHeaders: ['参数1', '参数2', '参数3'],
    paramRows: [],
    pasteText: '',
    searchResults: [],
    searchTimer: null
  })
}

const products = ref([createEmptyProduct(), createEmptyProduct()])

const ratioTotal = computed(() => products.value.reduce((sum, p) => sum + (p.ratio || 0), 0))

function addProduct() {
  products.value.push(createEmptyProduct())
}

function removeProduct(index) {
  products.value.splice(index, 1)
}

function onStockInput(pIndex) {
  const product = products.value[pIndex]
  clearTimeout(product.searchTimer)
  if (!product.stock_code.trim()) {
    product.searchResults = []
    return
  }
  product.searchTimer = setTimeout(async () => {
    try {
      const res = await searchStocks({ q: product.stock_code.trim(), page_size: 10 })
      product.searchResults = res.results || []
    } catch {
      product.searchResults = []
    }
  }, 300)
}

function selectStock(pIndex, stock) {
  const product = products.value[pIndex]
  product.stock_code = stock.code
  product.searchResults = []
}

function hideSearch(pIndex) {
  setTimeout(() => {
    products.value[pIndex].searchResults = []
  }, 200)
}

function addParamRow(pIndex) {
  const product = products.value[pIndex]
  product.paramRows.push(product.paramHeaders.map(() => ''))
}

function parsePaste(pIndex) {
  const product = products.value[pIndex]
  if (!product.pasteText.trim()) return
  const lines = product.pasteText.trim().split('\n')
  const parsed = lines.map((line) => line.split('\t'))
  if (parsed.length > 0 && parsed[0].length > product.paramHeaders.length) {
    product.paramHeaders = parsed[0].map((_, i) => `参数${i + 1}`)
  }
  product.paramRows.push(...parsed)
  product.pasteText = ''
}

async function handleImportExcel(file) {
  const formData = new FormData()
  formData.append('file', file)
  try {
    const res = await importExcel(formData)
    if (res.products && Array.isArray(res.products)) {
      products.value = res.products.map((p) => reactive({
        stock_code: p.stock_code || '',
        market_type: p.market_type || 'cn',
        years: p.years || [currentYear],
        ratio: p.ratio || 0,
        paramHeaders: p.headers || ['参数1', '参数2', '参数3'],
        paramRows: p.rows || [],
        pasteText: '',
        searchResults: [],
        searchTimer: null
      }))
    }
    ElMessage.success('Excel 导入成功')
  } catch {
    ElMessage.error('Excel 导入失败')
  }
  return false
}

async function submit() {
  if (ratioTotal.value !== 100) {
    ElMessage.error('产品比例总和必须为 100%')
    return
  }
  const hasEmpty = products.value.some((p) => !p.stock_code.trim())
  if (hasEmpty) {
    ElMessage.error('请为每个产品设置股票代码')
    return
  }

  submitting.value = true
  try {
    const productsConfig = products.value.map((p) => ({
      stock_code: p.stock_code,
      market_type: p.market_type,
      years: p.years,
      ratio: p.ratio,
      headers: p.paramHeaders,
      rows: p.paramRows
    }))

    const res = await createTask({
      name: form.task_name || `多产品回测-${new Date().toLocaleString()}`,
      task_type: 'backtest_multi_product',
      config: {
        token_id: form.token_id || null,
        commission: form.commission,
        products: productsConfig
      }
    })
    ElMessage.success('任务创建成功')
    setTimeout(() => router.push(`/backtest-multi/${res.task_id}`), 800)
  } catch {
    ElMessage.error('创建任务失败')
  } finally {
    submitting.value = false
  }
}

async function loadTokens() {
  try {
    const res = await getTokens()
    tokens.value = res.tokens || []
  } catch {}
}

onMounted(() => loadTokens())
</script>

<style scoped>
.full-width {
  width: 100%;
}

.backtest-multi-create-page__product-card {
  position: relative;
}

.backtest-multi-create-page__search-wrap {
  position: relative;
}

.backtest-multi-create-page__search-panel {
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

.backtest-multi-create-page__search-item {
  padding: 10px 12px;
  cursor: pointer;
  border-bottom: 1px solid rgba(30, 64, 175, 0.08);
}

.backtest-multi-create-page__search-item:last-child {
  border-bottom: none;
}

.backtest-multi-create-page__search-code {
  color: var(--app-text);
  font-size: 13px;
  font-weight: 700;
}

.backtest-multi-create-page__param-section {
  margin-top: 12px;
}

.backtest-multi-create-page__paste-area {
  margin-bottom: 12px;
}

.backtest-multi-create-page__ratio-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.backtest-multi-create-page__ratio-pill {
  font-weight: 600;
}

.backtest-multi-create-page__ratio-warn {
  margin-top: 8px;
  color: #dc2626;
  font-size: 13px;
}
</style>
