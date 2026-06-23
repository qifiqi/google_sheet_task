<template>
  <div class="app-page backtest-multi-preview-page">
    <PageToolbar
      eyebrow="Multi-Product Preview"
      title="多产品全局预览"
      :description="taskName || '加载中...'"
    >
      <template #actions>
        <el-button @click="exportXlsx">导出 XLSX</el-button>
        <el-button class="page-back-button" @click="$router.push(`/backtest-multi/${taskId}`)">返回详情</el-button>
      </template>
    </PageToolbar>

    <el-row :gutter="12" class="backtest-multi-preview-page__metrics">
      <el-col :xs="12" :sm="6">
        <div class="sub-card">
          <div class="panel-note">任务 ID</div>
          <div class="backtest-multi-preview-page__metric-id font-mono">{{ taskId }}</div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="6">
        <div class="sub-card">
          <div class="panel-note">结果总数</div>
          <div class="backtest-multi-preview-page__metric-value">{{ summary.total_results ?? '-' }}</div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="6">
        <div class="sub-card">
          <div class="panel-note">成功结果</div>
          <div class="backtest-multi-preview-page__metric-value backtest-multi-preview-page__metric-value--success">
            {{ summary.success_results ?? '-' }}
          </div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="6">
        <div class="sub-card">
          <div class="panel-note">产品分组</div>
          <div class="backtest-multi-preview-page__metric-value">{{ summary.group_count ?? '-' }}</div>
        </div>
      </el-col>
    </el-row>

    <div v-loading="loading" class="backtest-multi-preview-page__layout">
      <!-- Group Selector -->
      <el-card v-if="groups.length" shadow="never" class="page-section">
        <el-row :gutter="16" align="bottom">
          <el-col :xs="24" :md="6">
            <el-form-item label="产品分组">
              <el-select v-model="activeGroupKey" class="full-width" @change="onGroupChange">
                <el-option
                  v-for="group in groups"
                  :key="group.group_key"
                  :value="group.group_key"
                  :label="`${group.group_label} (${group.column_count} 组参数)`"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :md="18">
            <div v-if="activeGroup" class="control-row">
              <el-tag type="primary">{{ activeGroup.group_label }}</el-tag>
              <el-tag type="info">区间：{{ activeGroup.period || '-' }}</el-tag>
              <el-tag type="info">参数列数：{{ activeGroup.column_count || 0 }}</el-tag>
            </div>
          </el-col>
        </el-row>
      </el-card>

      <!-- Ratio Editing -->
      <el-card v-if="groups.length" shadow="never" class="page-section">
        <div class="section-heading">
          <h3 class="section-title section-title--muted">产品比例调整</h3>
          <div class="section-actions">
            <el-button size="small" type="primary" :loading="savingRatios" @click="saveRatios">保存比例</el-button>
          </div>
        </div>
        <div class="backtest-multi-preview-page__ratio-row">
          <div v-for="(ratio, rIndex) in ratios" :key="rIndex" class="backtest-multi-preview-page__ratio-item">
            <span class="backtest-multi-preview-page__ratio-label">{{ ratio.label }}</span>
            <el-input-number v-model="ratio.value" :min="0" :step="5" size="small" />
            <span class="panel-note">%</span>
          </div>
          <el-tag type="success" size="large">
            合计: {{ ratioTotal }}%
          </el-tag>
        </div>
      </el-card>

      <!-- Data Table -->
      <el-card shadow="never" class="page-section">
        <div v-if="!activeGroup || !activeGroup.rows?.length" class="panel-note panel-note--center backtest-multi-preview-page__empty">
          {{ loading ? '正在加载全局预览数据...' : '该分组下没有成功结果' }}
        </div>

        <div v-else class="backtest-multi-preview-page__table-wrap">
          <table class="backtest-multi-preview-page__table">
            <thead>
              <tr>
                <th class="sticky-col sticky-col-1">指标类型</th>
                <th class="sticky-col sticky-col-2">指标</th>
                <th class="sticky-col sticky-col-3">指数</th>
                <th
                  v-for="column in activeGroup.columns"
                  :key="column.column_key"
                >
                  <div class="backtest-multi-preview-page__head-title">
                    {{ column.header || `结果 ${column.result_id}` }}
                  </div>
                  <div class="panel-note">{{ column.result_id }}</div>
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, index) in activeGroup.rows" :key="index">
                <td class="sticky-col sticky-col-1 backtest-multi-preview-page__sticky-main">
                  {{ row.category || '-' }}
                </td>
                <td class="sticky-col sticky-col-2">{{ row.metric || '-' }}</td>
                <td class="sticky-col sticky-col-3">{{ row.index_value || '-' }}</td>
                <td v-for="column in activeGroup.columns" :key="column.column_key">
                  {{ row.values?.[column.column_key] ?? '-' }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getGlobalPreview, updateRatios, exportGlobalPreview } from '@/api/backtestMulti'
import PageToolbar from '@/components/PageToolbar.vue'

const route = useRoute()
const taskId = route.params.id
const loading = ref(false)
const savingRatios = ref(false)
const taskName = ref('')
const summary = ref({})
const groups = ref([])
const activeGroupKey = ref('')
const ratios = ref([])

const activeGroup = computed(() => groups.value.find((g) => g.group_key === activeGroupKey.value) || null)
const ratioTotal = computed(() => ratios.value.reduce((sum, r) => sum + (r.value || 0), 0))

function buildExcelDownloadName() {
  const safeName = String(taskName.value || taskId)
    .trim()
    .replace(/[\\/:*?"<>|]/g, '_')
    .replace(/[ .]+$/g, '')
  return `${safeName || taskId}.xlsx`
}

function onGroupChange() {}

async function loadData() {
  loading.value = true
  try {
    const res = await getGlobalPreview(taskId)
    if (res.status !== 'success') {
      throw new Error(res.message || '加载失败')
    }
    taskName.value = res.task?.name || taskId
    summary.value = res.summary || {}
    groups.value = res.groups || []
    if (groups.value.length) activeGroupKey.value = groups.value[0].group_key
    if (res.ratios && Array.isArray(res.ratios)) {
      ratios.value = res.ratios.map((r) => ({ ...r }))
    }
  } catch (error) {
    ElMessage.error(error.message || '加载全局预览失败')
  } finally {
    loading.value = false
  }
}

async function saveRatios() {
  savingRatios.value = true
  try {
    const data = ratios.value.map((r) => ({ label: r.label, value: r.value }))
    await updateRatios(taskId, { ratios: data })
    ElMessage.success('比例保存成功')
    loadData()
  } catch {
    ElMessage.error('保存比例失败')
  } finally {
    savingRatios.value = false
  }
}

async function exportXlsx() {
  try {
    const blob = await exportGlobalPreview(taskId)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = buildExcelDownloadName()
    link.click()
    URL.revokeObjectURL(url)
  } catch {
    ElMessage.error('导出失败')
  }
}

onMounted(loadData)
</script>

<style scoped>
.full-width {
  width: 100%;
}

.backtest-multi-preview-page__metrics {
  margin-bottom: 4px;
}

.backtest-multi-preview-page__metric-id {
  margin-top: 6px;
  word-break: break-all;
  color: var(--app-text);
  font-size: 13px;
  font-weight: 700;
}

.backtest-multi-preview-page__metric-value {
  margin-top: 6px;
  color: var(--app-text);
  font-size: 22px;
  font-weight: 700;
}

.backtest-multi-preview-page__metric-value--success {
  color: #16a34a;
}

.backtest-multi-preview-page__layout {
  display: grid;
  gap: 0;
}

.backtest-multi-preview-page__ratio-row {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: center;
}

.backtest-multi-preview-page__ratio-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.backtest-multi-preview-page__ratio-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text);
}

.backtest-multi-preview-page__empty {
  padding: 64px 0;
}

.backtest-multi-preview-page__table-wrap {
  overflow: auto;
  border: 1px solid var(--app-border);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.92);
}

.backtest-multi-preview-page__table {
  width: 100%;
  min-width: 960px;
  border-collapse: collapse;
}

.backtest-multi-preview-page__table th,
.backtest-multi-preview-page__table td {
  padding: 8px 12px;
  border: 1px solid rgba(30, 64, 175, 0.12);
  vertical-align: middle;
  text-align: center;
  font-size: 12px;
}

.backtest-multi-preview-page__table thead th {
  position: sticky;
  top: 0;
  z-index: 2;
  background: rgba(232, 239, 250, 0.82);
}

.sticky-col {
  position: sticky;
  z-index: 1;
  background: rgba(255, 255, 255, 0.98);
}

.sticky-col-1 {
  left: 0;
  min-width: 120px;
  background: #f7e1a1;
}

.sticky-col-2 {
  left: 120px;
  min-width: 180px;
}

.sticky-col-3 {
  left: 300px;
  min-width: 140px;
}

.backtest-multi-preview-page__table thead .sticky-col {
  z-index: 3;
  background: rgba(232, 239, 250, 0.96);
}

.backtest-multi-preview-page__table thead .sticky-col-1 {
  background: #f7e1a1;
}

.backtest-multi-preview-page__head-title,
.backtest-multi-preview-page__sticky-main {
  color: var(--app-text);
  font-weight: 700;
}
</style>
