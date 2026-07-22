<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { ArrowLeft, Download, Refresh, TrendCharts } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import AnalysisDetailTabs from '../../components/analysis/AnalysisDetailTabs.vue'
import AnalysisChartGrid from '../../components/analysis/AnalysisChartGrid.vue'
import AnalysisMetricGrid from '../../components/analysis/AnalysisMetricGrid.vue'
import AnalysisSourceForm from '../../components/analysis/AnalysisSourceForm.vue'
import { useAnalysisResult } from '../../composables/useAnalysisResult'
import type { AnalysisSource } from '../../types/analysis'
import { downloadFile } from '../../utils/download'
import '../../styles/analysis/analysis-result-page.css'

const props = defineProps<{
  source: AnalysisSource
  resultId?: string
}>()

const router = useRouter()
const analysis = useAnalysisResult(props.source)
const isXplSource = computed(() => props.source === 'xpl-v1')
const title = computed(() => isXplSource.value ? 'V1 回测数据分析' : '回测结果')
const subtitle = computed(() => isXplSource.value ? '从 Google Sheet 读取并分析 V1 回测数据' : '查看并导出当前任务的 V1 回测分析结果')
const backPath = computed(() => props.source === 'backtest-training' ? '/backtest/training/tasks' : '/backtest/multi-product/tasks')

async function loadResult() {
  if (!props.resultId) return
  try {
    await analysis.loadBacktestResult(props.resultId)
  } catch {
    ElMessage.error(analysis.errorMessage.value || '加载结果失败')
  }
}

async function loadWorksheets(spreadsheetId: string) {
  try {
    await analysis.loadWorksheets(spreadsheetId)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '获取工作表失败')
  }
}

async function analyzeV1(payload: { googleSheetUrl: string; spreadsheetId: string; worksheetName: string }) {
  try {
    await analysis.analyzeV1(payload)
    ElMessage.success('V1 分析完成')
  } catch {
    ElMessage.error(analysis.errorMessage.value || '分析失败')
  }
}

async function exportResult() {
  const result = analysis.result.value
  if (!result) return
  try {
    if (props.source === 'backtest-training' && props.resultId) {
      await downloadFile(`/backtest-training/api/task-result/${encodeURIComponent(props.resultId)}/export-preview/download`, `backtest_result_${props.resultId}.csv`)
    } else {
      const filename = props.source === 'xpl-v1' ? 'v1_analysis_details.csv' : `backtest_result_${props.resultId}.csv`
      await downloadFile('/xpl/export', filename, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename, analyze_result: result }),
      })
    }
    ElMessage.success('已开始下载')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '导出失败')
  }
}

function backToList() {
  router.push(backPath.value)
}

onMounted(() => {
  if (!isXplSource.value) loadResult()
})
</script>

<template>
  <section class="analysis-result-page">
    <header class="analysis-result-page__header">
      <div>
        <p>{{ isXplSource ? '业务模块' : '数据回测' }}</p>
        <h1>{{ title }}</h1>
        <span>{{ subtitle }}</span>
      </div>
      <div class="analysis-result-page__actions">
        <el-button v-if="!isXplSource" :icon="ArrowLeft" @click="backToList">返回列表</el-button>
        <el-button v-if="!isXplSource" :icon="Refresh" :loading="analysis.loading.value" @click="loadResult">刷新</el-button>
        <el-button type="primary" :icon="Download" :disabled="!analysis.result.value" @click="exportResult">导出</el-button>
      </div>
    </header>

    <AnalysisSourceForm
      v-if="isXplSource"
      :worksheets="analysis.worksheetNames.value"
      :spreadsheet-title="analysis.spreadsheetTitle.value"
      :loading="analysis.loading.value"
      @fetch-worksheets="loadWorksheets"
      @analyze="analyzeV1"
    />

    <el-alert v-if="analysis.errorMessage.value" :title="analysis.errorMessage.value" type="error" show-icon :closable="false" />
    <el-skeleton v-if="analysis.loading.value && !analysis.result.value && !isXplSource" :rows="10" animated />
    <template v-else>
      <AnalysisMetricGrid :result="analysis.result.value || undefined" />
      <AnalysisDetailTabs :result="analysis.result.value || undefined" />
      <section class="analysis-result-page__charts">
        <header><el-icon><TrendCharts /></el-icon><h2>V1 图表</h2><span>收益、风险与稳定性趋势</span></header>
        <AnalysisChartGrid :result="analysis.result.value || undefined" />
      </section>
      <el-empty v-if="!analysis.result.value && !isXplSource" description="暂无分析结果" :image-size="72" />
    </template>
  </section>
</template>
