<template>
  <div class="app-page xpl-index-page">
    <div class="page-toolbar">
      <div class="page-toolbar__meta">
        <div class="page-toolbar__eyebrow">XPL</div>
        <h2 class="page-title">数据分析工具</h2>
      </div>
      <div class="page-toolbar__actions page-toolbar__actions--tight">
        <el-button @click="refreshData">刷新</el-button>
        <el-button @click="exportResults">导出结果</el-button>
      </div>
    </div>

    <el-card shadow="never" class="section-card">
      <div class="section-label">数据输入</div>
      <el-row :gutter="16">
        <el-col :xs="24" :lg="10">
          <div class="xpl-input-panel">
            <div class="xpl-input-panel__head">
              <span class="section-label xpl-input-panel__title">粘贴数据</span>
              <div class="page-toolbar__actions page-toolbar__actions--tight">
                <el-button size="small" @click="pasteFromClipboard">粘贴</el-button>
                <el-button size="small" @click="loadSampleData">示例</el-button>
                <el-button size="small" type="danger" plain @click="clearAllData">清空</el-button>
              </div>
            </div>
            <el-input
              v-model="dataInput"
              type="textarea"
              :rows="10"
              placeholder="请将 Excel 中的时间列和收益率列数据粘贴到此处，格式为：时间 收益率&#10;例如：&#10;2025-01-01 0.0234&#10;2025-01-02 -0.0156"
              class="xpl-input-panel__textarea"
              @input="onDataInput"
            />
            <div class="xpl-input-panel__count">{{ lineCount }} 行数据</div>
          </div>
        </el-col>

        <el-col :xs="24" :lg="7">
          <el-card shadow="never" class="xpl-fill-card">
            <div class="section-label">分析设置</div>
            <el-form label-width="80px" size="small">
              <el-form-item label="时间格式">
                <el-select v-model="settings.timeFormat" class="full-width">
                  <el-option value="auto" label="自动识别" />
                  <el-option value="YYYY-MM-DD" label="YYYY-MM-DD" />
                  <el-option value="YYYY/MM/DD" label="YYYY/MM/DD" />
                  <el-option value="MM/DD/YYYY" label="MM/DD/YYYY" />
                </el-select>
              </el-form-item>
              <el-form-item label="分隔符">
                <el-select v-model="settings.delimiter" class="full-width">
                  <el-option value="auto" label="自动识别" />
                  <el-option value="tab" label="Tab" />
                  <el-option value="space" label="空格" />
                  <el-option value="comma" label="逗号" />
                </el-select>
              </el-form-item>
              <el-form-item label="基准收益">
                <el-input v-model="settings.benchmark" placeholder="如 0.08 (年化8%)" />
              </el-form-item>
              <el-form-item label="无风险利率">
                <el-input v-model="settings.riskFreeRate" placeholder="如 0.03" />
              </el-form-item>
            </el-form>
            <el-button type="primary" class="full-width" :loading="analyzing" @click="analyze">开始分析</el-button>
          </el-card>
        </el-col>

        <el-col :xs="24" :lg="7">
          <el-card shadow="never" class="xpl-fill-card">
            <div class="section-label">快速统计</div>
            <div v-if="quickStats">
              <el-descriptions :column="1" size="small">
                <el-descriptions-item label="数据行数">{{ quickStats.rows }}</el-descriptions-item>
                <el-descriptions-item label="时间范围">{{ quickStats.dateRange }}</el-descriptions-item>
                <el-descriptions-item label="累计收益">{{ quickStats.totalReturn }}</el-descriptions-item>
                <el-descriptions-item label="年化收益">{{ quickStats.annualReturn }}</el-descriptions-item>
              </el-descriptions>
            </div>
            <div v-else class="empty-note">输入数据后显示快速统计</div>
          </el-card>
        </el-col>
      </el-row>
    </el-card>

    <el-card v-if="analysisResult" shadow="never" class="section-card">
      <div class="section-label">分析结果</div>
      <el-row :gutter="12" class="xpl-metric-grid">
        <el-col v-for="m in metrics" :key="m.key" :xs="12" :sm="6" class="xpl-metric-grid__col">
          <el-card shadow="never" class="metric-card--center">
            <div class="card-grid-note">{{ m.label }}</div>
            <div class="xpl-metric-grid__value" :class="m.toneClass">{{ analysisResult[m.key] ?? '-' }}</div>
          </el-card>
        </el-col>
      </el-row>
      <el-table :data="analysisResult.details || []" stripe size="small" max-height="400">
        <el-table-column prop="date" label="日期" width="120" />
        <el-table-column prop="return" label="收益率" width="100" />
        <el-table-column prop="cumReturn" label="累计收益" width="120" />
        <el-table-column prop="drawdown" label="回撤" width="100" />
      </el-table>
    </el-card>

    <el-card shadow="never">
      <div class="section-label">其他工具</div>
      <el-button @click="$router.push('/xpl/v1')">V1: Google Sheet 分析</el-button>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { ElMessage } from 'element-plus'

const dataInput = ref('')
const analyzing = ref(false)
const analysisResult = ref(null)
const quickStats = ref(null)

const settings = reactive({ timeFormat: 'auto', delimiter: 'auto', benchmark: '', riskFreeRate: '0.03' })

const metrics = [
  { key: 'totalReturn', label: '累计收益', toneClass: 'xpl-metric-grid__value--primary' },
  { key: 'annualReturn', label: '年化收益', toneClass: 'xpl-metric-grid__value--success' },
  { key: 'maxDrawdown', label: '最大回撤', toneClass: 'xpl-metric-grid__value--danger' },
  { key: 'sharpe', label: 'Sharpe', toneClass: 'xpl-metric-grid__value--warning' },
  { key: 'calmar', label: 'Calmar', toneClass: 'xpl-metric-grid__value--muted' },
  { key: 'winRate', label: '胜率', toneClass: 'xpl-metric-grid__value--info' },
  { key: 'volatility', label: '波动率', toneClass: 'xpl-metric-grid__value--muted' },
  { key: 'tradingDays', label: '交易天数', toneClass: 'xpl-metric-grid__value--soft' },
]

const lineCount = computed(() => {
  if (!dataInput.value.trim()) return 0
  return dataInput.value.trim().split('\n').filter(l => l.trim()).length
})

function onDataInput() {
  if (!dataInput.value.trim()) {
    quickStats.value = null
    return
  }
  const lines = dataInput.value.trim().split('\n').filter(l => l.trim())
  quickStats.value = { rows: lines.length, dateRange: '-', totalReturn: '-', annualReturn: '-' }
}

async function pasteFromClipboard() {
  try {
    const text = await navigator.clipboard.readText()
    dataInput.value = text
    onDataInput()
  } catch {
    ElMessage.warning('无法访问剪贴板，请手动粘贴')
  }
}

function loadSampleData() {
  const today = new Date()
  const lines = []
  for (let i = 30; i >= 0; i -= 1) {
    const d = new Date(today)
    d.setDate(d.getDate() - i)
    const r = (Math.random() - 0.48) * 0.02
    lines.push(`${d.toISOString().slice(0, 10)} ${r.toFixed(4)}`)
  }
  dataInput.value = lines.join('\n')
  onDataInput()
}

function clearAllData() {
  dataInput.value = ''
  analysisResult.value = null
  quickStats.value = null
}

async function analyze() {
  if (!dataInput.value.trim()) {
    ElMessage.warning('请先输入数据')
    return
  }
  analyzing.value = true
  try {
    const lines = dataInput.value.trim().split('\n').filter(l => l.trim())
    const returns = lines.map(l => {
      const parts = l.trim().split(/[\t ,]+/)
      return parseFloat(parts[parts.length - 1])
    }).filter(v => !Number.isNaN(v))

    if (!returns.length) {
      ElMessage.error('无法解析数据，请检查格式')
      return
    }

    const total = returns.reduce((a, b) => a * (1 + b), 1) - 1
    const annual = Math.pow(1 + total, 252 / returns.length) - 1
    const mean = returns.reduce((a, b) => a + b, 0) / returns.length
    const std = Math.sqrt(returns.reduce((a, b) => a + Math.pow(b - mean, 2), 0) / returns.length)
    const sharpe = std > 0 ? ((annual - parseFloat(settings.riskFreeRate || 0)) / (std * Math.sqrt(252))).toFixed(3) : '-'
    let maxDD = 0
    let peak = 1
    let cum = 1
    for (const r of returns) {
      cum *= 1 + r
      if (cum > peak) peak = cum
      const dd = (peak - cum) / peak
      if (dd > maxDD) maxDD = dd
    }
    const wins = returns.filter(r => r > 0).length
    analysisResult.value = {
      totalReturn: `${(total * 100).toFixed(2)}%`,
      annualReturn: `${(annual * 100).toFixed(2)}%`,
      maxDrawdown: `${(maxDD * 100).toFixed(2)}%`,
      sharpe,
      calmar: maxDD > 0 ? (annual / maxDD).toFixed(3) : '-',
      winRate: `${((wins / returns.length) * 100).toFixed(1)}%`,
      volatility: `${(std * Math.sqrt(252) * 100).toFixed(2)}%`,
      tradingDays: returns.length,
      details: []
    }
    ElMessage.success('分析完成')
  } finally {
    analyzing.value = false
  }
}

function refreshData() {
  if (dataInput.value) analyze()
}

function exportResults() {
  if (!analysisResult.value) {
    ElMessage.warning('请先进行分析')
    return
  }
  const data = JSON.stringify(analysisResult.value, null, 2)
  const blob = new Blob([data], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'analysis_result.json'
  a.click()
  URL.revokeObjectURL(url)
}
</script>

<style scoped>
.xpl-input-panel {
  padding: 12px;
  border: 1px solid var(--app-border);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.74);
}

.xpl-input-panel__head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.xpl-input-panel__title {
  margin: 0;
}

.xpl-input-panel__textarea :deep(textarea) {
  font-family: 'Fira Code', monospace;
}

.xpl-input-panel__count {
  margin-top: 4px;
  text-align: right;
  color: var(--app-text-muted);
  font-size: var(--app-font-xs);
}

.xpl-fill-card {
  height: 100%;
}

.xpl-metric-grid {
  margin-bottom: 16px;
}

.xpl-metric-grid__col {
  margin-bottom: 12px;
}

.xpl-metric-grid__value {
  margin-top: 4px;
  font-size: 22px;
  font-weight: 700;
}

.xpl-metric-grid__value--primary {
  color: #409eff;
}

.xpl-metric-grid__value--success {
  color: #67c23a;
}

.xpl-metric-grid__value--danger {
  color: #f56c6c;
}

.xpl-metric-grid__value--warning {
  color: #e6a23c;
}

.xpl-metric-grid__value--muted {
  color: #909399;
}

.xpl-metric-grid__value--info {
  color: #17a2b8;
}

.xpl-metric-grid__value--soft {
  color: #606266;
}

@media (max-width: 767px) {
  .xpl-input-panel__head {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
