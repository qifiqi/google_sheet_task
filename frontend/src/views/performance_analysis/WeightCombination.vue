<template>
  <div class="app-page weight-combination-page">
    <PageToolbar
      eyebrow="绩效分析"
      title="权重组合分析"
      description="按步长穷举组合权重，流式接收每个组合的年化收益、最大回撤指标。"
    >
      <template #actions>
        <el-button class="page-back-button" @click="$router.push('/performance_analysis')">返回</el-button>
      </template>
    </PageToolbar>

    <el-card shadow="never" class="weight-combination-page__section">
      <template #header><span>参数配置</span></template>
      <el-form :model="form" inline label-position="top" @submit.prevent="handleAnalyze">
        <el-form-item label="任务 ID" required>
          <el-input v-model="form.taskId" placeholder="输入任务 ID" style="width: 220px" />
        </el-form-item>
        <el-form-item label="步长(%)">
          <el-input-number v-model="form.step" :min="1" :max="100" :step="1" />
        </el-form-item>
        <el-form-item label="上限(%)">
          <el-input-number v-model="form.maxWeight" :min="1" :max="100" :step="1" />
        </el-form-item>
        <el-form-item label="下限(%)">
          <el-input-number v-model="form.minWeight" :min="0" :max="100" :step="1" />
        </el-form-item>
        <el-form-item label="单股上限(%)">
          <el-input-number v-model="form.singleCap" :min="1" :max="100" :step="1" />
        </el-form-item>
        <el-form-item label=" ">
          <el-button type="primary" :loading="analyzing" @click="handleAnalyze">开始分析</el-button>
          <el-button v-if="analyzing" type="danger" @click="handleCancel">取消</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card v-if="analyzing || progressVisible" shadow="never" class="weight-combination-page__section">
      <template #header><span>分析进度</span></template>
      <el-progress
        :percentage="progressPercent >= 0 ? progressPercent : 100"
        :indeterminate="progressPercent < 0"
        :stroke-width="16"
      />
      <div class="weight-combination-page__progress-info">{{ progressInfo }}</div>
    </el-card>

    <el-card v-if="rows.length" shadow="never">
      <template #header>
        <div class="weight-combination-page__results-head">
          <div>
            <span>组合分析结果</span>
            <el-tag type="success" size="small" class="weight-combination-page__stat">{{ filteredRows.length }} 条显示</el-tag>
            <el-tag type="primary" size="small" class="weight-combination-page__stat">{{ rows.length }} 条总计</el-tag>
          </div>
          <div>
            <el-button size="small" type="success" @click="exportCsv">导出 CSV</el-button>
            <el-button size="small" @click="clearFilters">清除筛选</el-button>
          </div>
        </div>
      </template>

      <el-table :data="filteredRows" height="600" border>
        <el-table-column type="index" label="#" width="60" align="center" />
        <el-table-column
          label="股票组合"
          prop="stocks_display"
          min-width="240"
          show-overflow-tooltip
        />
        <el-table-column
          v-for="col in numericColumns"
          :key="col.prop"
          :prop="col.prop"
          :width="col.width"
          align="right"
          sortable
        >
          <template #header>
            <el-popover placement="bottom-end" :width="220" trigger="click" @show="seedDraft(col.prop)">
              <template #reference>
                <span class="weight-combination-page__col-head" @click.stop>
                  {{ col.label }}
                  <el-icon class="weight-combination-page__funnel" :class="{ 'is-active': hasActiveFilter(col.prop) }">
                    <Filter />
                  </el-icon>
                </span>
              </template>
              <div class="weight-combination-page__filter">
                <el-input v-model="filterDrafts[col.prop].min" type="number" placeholder="最小值（不限）" size="small" />
                <el-input v-model="filterDrafts[col.prop].max" type="number" placeholder="最大值（不限）" size="small" />
                <div v-if="filterDrafts[col.prop].invalid" class="weight-combination-page__filter-hint">最小值不能大于最大值</div>
                <div class="weight-combination-page__filter-actions">
                  <el-button size="small" @click="clearRangeFilter(col.prop)">清除</el-button>
                  <el-button size="small" type="primary" @click="applyRangeFilter(col.prop)">应用</el-button>
                </div>
              </div>
            </el-popover>
          </template>
          <template #default="{ row }">
            {{ formatNumber(row[col.prop], col.digits, col.suffix) }}
          </template>
        </el-table-column>
        <el-table-column label="查看" width="90" align="center" fixed="right">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="openGlobalPreviewWithRatios(row)">查看</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Filter } from '@element-plus/icons-vue'
import PageToolbar from '@/components/PageToolbar.vue'
import { analyzeWeightCombinationStream } from '@/api/performance_analysis'

const route = useRoute()
const router = useRouter()

const form = reactive({
  taskId: '',
  step: 5,
  maxWeight: 100,
  minWeight: 50,
  singleCap: 30,
})

const analyzing = ref(false)
const progressVisible = ref(false)
const progressPercent = ref(0)
const progressInfo = ref('准备中...')
let abortController = null

// 结果行（已 transform）；流式接收时先攒 batch 再落 ref，避免每行触发整表重渲染
const rows = ref([])
let pendingRows = []

const numericColumns = [
  { prop: 'index_rate_disp', label: '年化收益率(指数)', width: 185, digits: 2, suffix: '%' },
  { prop: 'start_rate_disp', label: '年化收益率(策略)', width: 185, digits: 2, suffix: '%' },
  { prop: 'index_dd_disp', label: '最大回撤(指数)', width: 175, digits: 2, suffix: '%' },
  { prop: 'start_dd_disp', label: '最大回撤(策略)', width: 175, digits: 2, suffix: '%' },
  { prop: 'weight_sum', label: '权重和(%)', width: 140, digits: 0, suffix: '%' },
]

// 已生效的范围筛选：prop -> { min: number|null, max: number|null }
const rangeFilters = reactive({})
// 弹窗内草稿：prop -> { min, max, invalid }
const filterDrafts = reactive({})

numericColumns.forEach((col) => {
  rangeFilters[col.prop] = { min: null, max: null }
  filterDrafts[col.prop] = { min: '', max: '', invalid: false }
})

function hasActiveFilter(prop) {
  const f = rangeFilters[prop]
  return !!(f && (f.min !== null || f.max !== null))
}

function seedDraft(prop) {
  const f = rangeFilters[prop]
  filterDrafts[prop].min = f.min !== null ? String(f.min) : ''
  filterDrafts[prop].max = f.max !== null ? String(f.max) : ''
  filterDrafts[prop].invalid = false
}

function applyRangeFilter(prop) {
  const draft = filterDrafts[prop]
  const min = draft.min === '' ? null : parseFloat(draft.min)
  const max = draft.max === '' ? null : parseFloat(draft.max)
  if (min !== null && max !== null && min > max) {
    draft.invalid = true
    return
  }
  rangeFilters[prop] = { min, max }
  draft.invalid = false
}

function clearRangeFilter(prop) {
  rangeFilters[prop] = { min: null, max: null }
  filterDrafts[prop].min = ''
  filterDrafts[prop].max = ''
  filterDrafts[prop].invalid = false
}

function clearFilters() {
  numericColumns.forEach((col) => {
    rangeFilters[col.prop] = { min: null, max: null }
  })
}

const filteredRows = computed(() =>
  rows.value.filter((row) =>
    numericColumns.every((col) => {
      const f = rangeFilters[col.prop]
      if (f.min === null && f.max === null) return true
      // 空值/非数值放行（与静态版 minMaxFilterFunction 一致）
      const raw = row[col.prop]
      if (raw === null || raw === undefined || raw === '') return true
      const value = parseFloat(raw)
      if (Number.isNaN(value)) return true
      if (f.min !== null && value < f.min) return false
      if (f.max !== null && value > f.max) return false
      return true
    })
  )
)

function formatNumber(value, digits, suffix) {
  if (value === null || value === undefined || value === '') return '-'
  return `${Number(value).toFixed(digits)}${suffix}`
}

function validateForm() {
  const { taskId, step, maxWeight, minWeight, singleCap } = form
  if (!taskId.trim()) { ElMessage.warning('请输入任务 ID'); return false }
  if (step < 1 || step > 100) { ElMessage.warning('权重步长必须在 1-100 之间'); return false }
  if (100 % step !== 0) { ElMessage.warning('权重步长必须能整除 100'); return false }
  if (maxWeight < 1 || maxWeight > 100) { ElMessage.warning('组合总权重上限必须在 1-100 之间'); return false }
  if (minWeight < 0 || minWeight > 100) { ElMessage.warning('组合总权重下限必须在 0-100 之间'); return false }
  if (minWeight > maxWeight) { ElMessage.warning('组合总权重下限不能大于上限'); return false }
  if (singleCap < 1 || singleCap > 100) { ElMessage.warning('单只股票权重上限必须在 1-100 之间'); return false }
  if (maxWeight % step !== 0 || minWeight % step !== 0 || singleCap % step !== 0) {
    ElMessage.warning('所有权重参数必须是步长的整数倍')
    return false
  }
  if (singleCap < step) { ElMessage.warning('单只股票权重上限不能小于步长'); return false }
  return true
}

// 数据转换：生成 *_disp 字段（原始值 × 100）与展示串（与静态版 transformData 一致）
function transformData(item) {
  item.weight_sum = item.stocks.reduce((sum, stock) => sum + stock.ratio, 0)
  const indexRate = item.annualized_rates?.index
  const startRate = item.annualized_rates?.start
  const indexDd = item.year_max_drawdown?.index
  const startDd = item.year_max_drawdown?.start
  item.index_rate_disp = indexRate != null ? Number(indexRate) * 100 : null
  item.start_rate_disp = startRate != null ? Number(startRate) * 100 : null
  item.index_dd_disp = indexDd != null ? Number(indexDd) * 100 : null
  item.start_dd_disp = startDd != null ? Number(startDd) * 100 : null
  item.stocks_display = item.stocks
    .filter((s) => s.ratio > 0)
    .map((s) => `${s.stock_name || s.stock_code || 'N/A'} (${s.ratio}%)`)
    .join(', ')
  return item
}

async function handleAnalyze() {
  if (analyzing.value) return
  if (!validateForm()) return

  analyzing.value = true
  progressVisible.value = true
  rows.value = []
  pendingRows = []
  progressPercent.value = 0
  progressInfo.value = '正在发送请求...'

  let processedCount = 0
  try {
    abortController = new AbortController()
    await analyzeWeightCombinationStream(
      {
        task_id: form.taskId.trim(),
        step: form.step,
        max_weight: form.maxWeight,
        min_weight: form.minWeight,
        single_cap: form.singleCap,
      },
      {
        signal: abortController.signal,
        onRow(data) {
          pendingRows.push(transformData(data))
          processedCount++
          if (processedCount % 20 === 0) {
            rows.value = rows.value.concat(pendingRows)
            pendingRows = []
            progressPercent.value = -1
            progressInfo.value = `已接收 ${processedCount} 条组合...`
          }
        },
      },
    )
    if (pendingRows.length) {
      rows.value = rows.value.concat(pendingRows)
      pendingRows = []
    }
    progressPercent.value = 100
    progressInfo.value = `分析完成！共生成 ${rows.value.length} 个组合`
    setTimeout(() => {
      progressVisible.value = false
    }, 2000)
  } catch (error) {
    if (error.name === 'AbortError') {
      progressInfo.value = '分析已取消'
      setTimeout(() => {
        progressVisible.value = false
      }, 1500)
    } else {
      progressInfo.value = '分析失败'
      ElMessage.error(`分析失败: ${error.message}`)
    }
  } finally {
    analyzing.value = false
    abortController = null
  }
}

function handleCancel() {
  abortController?.abort()
}

// 携带组合比例新标签打开多品全局预览（与静态版 openGlobalPreviewWithRatios 一致）
function openGlobalPreviewWithRatios(row) {
  if (!form.taskId.trim()) {
    ElMessage.warning('缺少任务 ID，无法跳转全局预览')
    return
  }
  const ratios = (row.stocks || [])
    .filter((s) => s && s.stock_code && Number(s.ratio) > 0)
    .map((s) => ({ stock_code: s.stock_code, ratio: Number(s.ratio) }))
  if (!ratios.length) {
    ElMessage.warning('该组合没有可用的股票比例')
    return
  }
  const { href } = router.resolve({
    name: 'BacktestMultiGlobalPreview',
    params: { id: form.taskId.trim() },
    query: { ratios: JSON.stringify(ratios) },
  })
  window.open(href, '_blank')
}

function exportCsv() {
  // 与静态版 Tabulator table.download('csv') 输出对齐：首列 # 行号，数值按 formatter 带后缀
  const header = ['#', '股票组合', ...numericColumns.map((c) => c.label)]
  const lines = [header]
  filteredRows.value.forEach((row, index) => {
    lines.push([
      String(index + 1),
      `"${row.stocks_display.replace(/"/g, '""')}"`,
      ...numericColumns.map((c) => formatNumber(row[c.prop], c.digits, c.suffix)),
    ])
  })
  const csv = '\uFEFF' + lines.map((line) => line.join(',')).join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `weight_combination_${Date.now()}.csv`
  link.click()
  URL.revokeObjectURL(url)
}

onMounted(() => {
  const taskId = route.query.task_id
  if (taskId) form.taskId = String(taskId)
})

onBeforeUnmount(() => {
  abortController?.abort()
})
</script>

<style scoped>
.weight-combination-page__section {
  margin-bottom: 16px;
}

.weight-combination-page__progress-info {
  margin-top: 8px;
  font-size: var(--app-font-xs, 12px);
  color: var(--app-text-muted, #909399);
}

.weight-combination-page__results-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
}

.weight-combination-page__stat {
  margin-left: 8px;
}

.weight-combination-page__col-head {
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}

.weight-combination-page__funnel {
  color: var(--app-text-muted, #909399);
}

.weight-combination-page__funnel.is-active {
  color: var(--el-color-primary);
}

.weight-combination-page__filter {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.weight-combination-page__filter-hint {
  font-size: var(--app-font-xs, 12px);
  color: var(--el-color-danger);
}

.weight-combination-page__filter-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
