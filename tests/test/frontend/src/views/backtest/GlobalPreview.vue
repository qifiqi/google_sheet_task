<template>
  <div class="app-page backtest-preview-page">
    <div class="page-toolbar">
      <div class="page-toolbar__meta">
        <div class="page-toolbar__eyebrow">Extended View</div>
        <h2 class="page-title">全局预览页</h2>
        <p class="page-description">{{ taskName || '加载中...' }}</p>
      </div>
      <div class="page-toolbar__actions">
        <el-button @click="exportXlsx">导出 XLSX</el-button>
        <el-button class="page-back-button" @click="$router.push(`/backtest/${taskId}`)">返回详情</el-button>
      </div>
    </div>

    <el-row :gutter="12" class="backtest-preview-page__metrics">
      <el-col :xs="12" :sm="6" class="backtest-preview-page__metric-col">
        <div class="sub-card backtest-preview-page__metric-card">
          <div class="panel-note">任务 ID</div>
          <div class="backtest-preview-page__metric-id font-mono">{{ taskId }}</div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="6" class="backtest-preview-page__metric-col">
        <div class="sub-card backtest-preview-page__metric-card">
          <div class="panel-note">结果总数</div>
          <div class="backtest-preview-page__metric-value">{{ summary.total_results ?? '-' }}</div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="6" class="backtest-preview-page__metric-col">
        <div class="sub-card backtest-preview-page__metric-card">
          <div class="backtest-preview-page__metric-label backtest-preview-page__metric-label--success">成功结果</div>
          <div class="backtest-preview-page__metric-value backtest-preview-page__metric-value--success">
            {{ summary.success_results ?? '-' }}
          </div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="6" class="backtest-preview-page__metric-col">
        <div class="sub-card backtest-preview-page__metric-card">
          <div class="panel-note">年份分组</div>
          <div class="backtest-preview-page__metric-value">{{ summary.group_count ?? '-' }}</div>
        </div>
      </el-col>
    </el-row>

    <div v-loading="loading" class="backtest-preview-page__layout">
      <el-card v-if="groups.length" shadow="never" class="page-section">
        <el-row :gutter="16" align="bottom">
          <el-col :xs="24" :md="6">
            <el-form-item label="年份分组">
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
              <el-tag type="danger">失败结果：{{ activeGroup.failed_results || 0 }}</el-tag>
            </div>
          </el-col>
        </el-row>
      </el-card>

      <el-card shadow="never" class="page-section">
        <div v-if="!activeGroup || !activeGroup.rows?.length" class="panel-note panel-note--center backtest-preview-page__empty">
          {{ loading ? '正在加载全局预览数据...' : '该分组下没有成功结果' }}
        </div>

        <div v-else class="backtest-preview-page__table-wrap">
          <table class="backtest-preview-page__table">
            <thead>
              <tr>
                <th class="sticky-col sticky-col-1">指标类型</th>
                <th class="sticky-col sticky-col-2">指标</th>
                <th class="sticky-col sticky-col-3">指数</th>
                <th
                  v-for="column in activeGroup.columns"
                  :key="column.column_key"
                  class="backtest-preview-page__dynamic-head"
                >
                  <div class="backtest-preview-page__head-title">
                    {{ column.header || `结果 ${column.result_id}` }}
                  </div>
                  <div class="panel-note">结果 ID: {{ column.result_id }}</div>
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, index) in activeGroup.rows" :key="index">
                <td class="sticky-col sticky-col-1 backtest-preview-page__sticky-main">
                  {{ row.category || '-' }}
                </td>
                <td class="sticky-col sticky-col-2">{{ row.metric || '-' }}</td>
                <td class="sticky-col sticky-col-3 backtest-preview-page__index-col">
                  {{ row.index_value || '-' }}
                </td>
                <td
                  v-for="column in activeGroup.columns"
                  :key="column.column_key"
                  class="backtest-preview-page__value-cell"
                >
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
import { getGlobalPreview, exportGlobalPreview } from '@/api/backtest'

const route = useRoute()
const taskId = route.params.id
const loading = ref(false)
const taskName = ref('')
const summary = ref({})
const groups = ref([])
const activeGroupKey = ref('')

const activeGroup = computed(() => groups.value.find((group) => group.group_key === activeGroupKey.value) || null)

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
  } catch (error) {
    ElMessage.error(error.message || '加载全局预览失败')
  } finally {
    loading.value = false
  }
}

async function exportXlsx() {
  try {
    const blob = await exportGlobalPreview(taskId)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `global_preview_${taskId}.xlsx`
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

.backtest-preview-page__metrics {
  margin-bottom: 4px;
}

.backtest-preview-page__metric-col {
  margin-bottom: 12px;
}

.backtest-preview-page__metric-card {
  height: 100%;
}

.backtest-preview-page__metric-id {
  margin-top: 6px;
  word-break: break-all;
  color: var(--app-text);
  font-size: 13px;
  font-weight: 700;
}

.backtest-preview-page__metric-label--success,
.backtest-preview-page__metric-value--success {
  color: #16a34a;
}

.backtest-preview-page__metric-value {
  margin-top: 6px;
  color: var(--app-text);
  font-size: 22px;
  font-weight: 700;
}

.backtest-preview-page__layout {
  display: grid;
  gap: 0;
}

.backtest-preview-page__empty {
  padding: 64px 0;
}

.backtest-preview-page__table-wrap {
  overflow: auto;
  border: 1px solid var(--app-border);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.92);
}

.backtest-preview-page__table {
  width: 100%;
  min-width: 960px;
  border-collapse: collapse;
}

.backtest-preview-page__table th,
.backtest-preview-page__table td {
  padding: 8px 12px;
  border: 1px solid rgba(30, 64, 175, 0.12);
  vertical-align: middle;
  text-align: center;
  font-size: 12px;
}

.backtest-preview-page__table thead th {
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

.backtest-preview-page__table thead .sticky-col {
  z-index: 3;
  background: rgba(232, 239, 250, 0.96);
}

.backtest-preview-page__table thead .sticky-col-1 {
  background: #f7e1a1;
}

.backtest-preview-page__dynamic-head {
  min-width: 180px;
  white-space: normal;
}

.backtest-preview-page__head-title,
.backtest-preview-page__sticky-main {
  color: var(--app-text);
  font-weight: 700;
}

.backtest-preview-page__index-col {
  color: var(--app-text-muted);
}

.backtest-preview-page__value-cell {
  white-space: nowrap;
}
</style>
