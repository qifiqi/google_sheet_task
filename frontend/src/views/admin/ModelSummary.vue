<template>
  <div class="admin-model-summary">
    <PageToolbar eyebrow="管理中心" title="模型汇总" description="查看和管理模型汇总数据">
      <template #actions>
        <el-button @click="handleExport" :loading="exporting">
          <el-icon><Download /></el-icon> 导出 CSV
        </el-button>
        <el-button type="warning" @click="handleRebuild" :loading="rebuilding">
          <el-icon><Refresh /></el-icon> 重建汇总
        </el-button>
      </template>
    </PageToolbar>

    <!-- Market Filter Cards -->
    <el-row :gutter="12" class="mb-4">
      <el-col :span="12">
        <div
          class="market-card"
          :class="{ 'market-card--active': activeMarket === 'cn' }"
          @click="switchMarket('cn')"
        >
          <div class="market-card__label">A股市场</div>
          <div class="market-card__value">{{ marketStats.cn }}</div>
        </div>
      </el-col>
      <el-col :span="12">
        <div
          class="market-card"
          :class="{ 'market-card--active': activeMarket === 'en' }"
          @click="switchMarket('en')"
        >
          <div class="market-card__label">美股市场</div>
          <div class="market-card__value">{{ marketStats.en }}</div>
        </div>
      </el-col>
    </el-row>

    <!-- Summary Stats -->
    <StatCardGrid
      :cards="STAT_CARDS"
      :data="summaryStats"
      :columns="{ xs: 12, sm: 8, md: 6 }"
      variant="gradient"
      class="mb-4"
    />

    <!-- Data Table -->
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>汇总数据</span>
          <el-button text type="primary" @click="loadData">
            <el-icon><Refresh /></el-icon> 刷新
          </el-button>
        </div>
      </template>
      <el-table :data="tableData" v-loading="loading" stripe style="width: 100%">
        <el-table-column prop="model_name" label="模型名称" min-width="160" show-overflow-tooltip />
        <el-table-column prop="market" label="市场" width="80" align="center">
          <template #default="{ row }">
            <el-tag size="small">{{ row.market === 'cn' ? 'A股' : '美股' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="total_tasks" label="任务数" width="90" align="right" />
        <el-table-column prop="avg_return" label="平均收益" width="110" align="right">
          <template #default="{ row }">
            <span :class="row.avg_return >= 0 ? 'text-success' : 'text-danger'">
              {{ formatPercent(row.avg_return) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="max_drawdown" label="最大回撤" width="110" align="right">
          <template #default="{ row }">
            <span class="text-danger">{{ formatPercent(row.max_drawdown) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="sharpe_ratio" label="夏普比率" width="100" align="right" />
        <el-table-column prop="win_rate" label="胜率" width="90" align="right">
          <template #default="{ row }">{{ formatPercent(row.win_rate) }}</template>
        </el-table-column>
        <el-table-column prop="updated_at" label="更新时间" width="170">
          <template #default="{ row }"><span class="cell-time">{{ formatTime(row.updated_at) }}</span></template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Rebuild Status -->
    <el-dialog v-model="rebuildStatusVisible" title="重建进度" width="400px" :close-on-click-modal="false">
      <div class="rebuild-status">
        <el-progress :percentage="rebuildProgress" :status="rebuildProgress === 100 ? 'success' : ''" />
        <p class="rebuild-status__text">{{ rebuildMessage }}</p>
      </div>
      <template #footer>
        <el-button @click="rebuildStatusVisible = false" :disabled="rebuilding">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { Download, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { modelSummary, exportModelSummary, rebuildModelSummary, getRebuildStatus } from '@/api/admin'
import PageToolbar from '@/components/PageToolbar.vue'
import StatCardGrid from '@/components/StatCardGrid.vue'

const loading = ref(false)
const exporting = ref(false)
const rebuilding = ref(false)
const tableData = ref([])
const activeMarket = ref('cn')
const marketStats = ref({ cn: 0, en: 0 })

const summaryStats = ref({ total_models: 0, avg_return: 0, avg_sharpe: 0, avg_win_rate: 0 })

const STAT_CARDS = [
  { key: 'total_models', label: '模型总数', background: 'linear-gradient(135deg, #6366f1, #4f46e5)' },
  { key: 'avg_return', label: '平均收益', background: 'linear-gradient(135deg, #10b981, #059669)' },
  { key: 'avg_sharpe', label: '平均夏普', background: 'linear-gradient(135deg, #f59e0b, #d97706)' },
  { key: 'avg_win_rate', label: '平均胜率', background: 'linear-gradient(135deg, #3b82f6, #1d4ed8)' },
]

// Rebuild status
const rebuildStatusVisible = ref(false)
const rebuildProgress = ref(0)
const rebuildMessage = ref('')
let rebuildTimer = null

function formatTime(str) {
  if (!str) return '-'
  return new Date(str).toLocaleString('zh-CN')
}

function formatPercent(val) {
  if (val == null) return '-'
  return `${(Number(val) * 100).toFixed(2)}%`
}

function switchMarket(market) {
  activeMarket.value = market
  loadData()
}

async function loadData() {
  loading.value = true
  try {
    const res = await modelSummary({ market: activeMarket.value })
    const data = res?.data || res || {}
    const items = data.items || data.summaries || data || []
    tableData.value = Array.isArray(items) ? items : []

    // Update stats
    marketStats.value = {
      cn: data.cn_count ?? tableData.value.filter(r => r.market === 'cn').length,
      en: data.en_count ?? tableData.value.filter(r => r.market === 'en').length,
    }

    if (tableData.value.length) {
      const returns = tableData.value.map(r => r.avg_return || 0)
      const sharpes = tableData.value.map(r => r.sharpe_ratio || 0)
      const wins = tableData.value.map(r => r.win_rate || 0)
      summaryStats.value = {
        total_models: tableData.value.length,
        avg_return: returns.reduce((a, b) => a + b, 0) / returns.length,
        avg_sharpe: (sharpes.reduce((a, b) => a + b, 0) / sharpes.length).toFixed(2),
        avg_win_rate: wins.reduce((a, b) => a + b, 0) / wins.length,
      }
    }
  } catch {
    tableData.value = []
  } finally {
    loading.value = false
  }
}

async function handleExport() {
  exporting.value = true
  try {
    const res = await exportModelSummary({ market: activeMarket.value })
    const blob = new Blob([res], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `model-summary-${activeMarket.value}-${Date.now()}.csv`
    link.click()
    URL.revokeObjectURL(url)
    ElMessage.success('导出成功')
  } catch {
    ElMessage.error('导出失败')
  } finally {
    exporting.value = false
  }
}

async function handleRebuild() {
  rebuilding.value = true
  rebuildProgress.value = 0
  rebuildMessage.value = '正在启动重建...'
  rebuildStatusVisible.value = true
  try {
    await rebuildModelSummary()
    pollRebuildStatus()
  } catch {
    ElMessage.error('启动重建失败')
    rebuilding.value = false
  }
}

function pollRebuildStatus() {
  rebuildTimer = window.setInterval(async () => {
    try {
      const res = await getRebuildStatus()
      const data = res?.data || res || {}
      rebuildProgress.value = data.progress ?? 0
      rebuildMessage.value = data.message || `进度: ${rebuildProgress.value}%`
      if (data.status === 'completed' || rebuildProgress.value >= 100) {
        window.clearInterval(rebuildTimer)
        rebuildTimer = null
        rebuilding.value = false
        rebuildProgress.value = 100
        rebuildMessage.value = '重建完成！'
        ElMessage.success('模型汇总重建完成')
        loadData()
      } else if (data.status === 'failed') {
        window.clearInterval(rebuildTimer)
        rebuildTimer = null
        rebuilding.value = false
        rebuildMessage.value = '重建失败'
        ElMessage.error('重建失败')
      }
    } catch {
      // ignore
    }
  }, 3000)
}

onBeforeUnmount(() => {
  if (rebuildTimer) {
    window.clearInterval(rebuildTimer)
  }
})

onMounted(loadData)
</script>

<style lang="scss" scoped>
.mb-4 { margin-bottom: 16px; }

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.market-card {
  padding: 16px 20px;
  border-radius: var(--el-border-radius-base);
  border: 2px solid var(--app-border);
  cursor: pointer;
  transition: all 0.2s;
  background: var(--app-surface);

  &:hover {
    border-color: var(--el-color-primary);
  }

  &--active {
    border-color: var(--el-color-primary);
    background: var(--el-color-primary-light-9);
  }

  &__label {
    font-size: var(--app-font-xs);
    color: var(--app-text-muted);
    margin-bottom: 4px;
  }

  &__value {
    font-size: 24px;
    font-weight: 700;
    color: var(--app-text);
  }
}

.text-success { color: #10b981; }
.text-danger { color: #ef4444; }

.cell-time {
  font-size: var(--app-font-sm);
  color: var(--app-text-muted);
  white-space: nowrap;
}

.rebuild-status {
  text-align: center;
  padding: 16px 0;

  &__text {
    margin-top: 12px;
    color: var(--app-text-muted);
  }
}
</style>
