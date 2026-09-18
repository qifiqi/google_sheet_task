<template>
  <div class="app-page admin-results-page">
    <PageToolbar eyebrow="管理后台" title="结果查询" />

    <!-- 成功/失败计数随筛选联动（/api/results 同过滤条件统计） -->
    <FilterToolbar v-model="filters" :filters="filterDefs" @search="doFilter" @clear="clearFilters" />

    <DataTableCard
      :data="results"
      :loading="loading"
      :total="total"
      v-model:page="page"
      v-model:page-size="pageSize"
      :page-sizes="[10, 20, 50, 100]"
      @page-change="loadResults"
    >
      <template #header-extra>
        <span class="admin-results-page__summary">
          共 <strong>{{ total }}</strong> 条
          <span class="admin-results-page__summary-success">成功 {{ summary.success }}</span>
          <span class="admin-results-page__summary-failed">失败 {{ summary.failed }}</span>
        </span>
      </template>

      <el-table-column prop="id" label="ID" width="80" />
      <el-table-column label="任务" min-width="220">
        <template #default="{ row }">
          <div class="admin-results-page__task-name">{{ row.task_name || '未知任务' }}</div>
          <div class="admin-results-page__task-meta">
            <el-tag size="small" type="info" effect="plain">{{ taskTypeLabel(row.task_type) }}</el-tag>
            <el-tooltip :content="row.task_id" placement="top" :show-after="200">
              <span class="admin-results-page__task-id">{{ shortTaskId(row.task_id) }}</span>
            </el-tooltip>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="步骤" width="70" align="center">
        <template #default="{ row }">{{ row.step_index ?? '-' }}</template>
      </el-table-column>
      <el-table-column label="状态" width="80" align="center">
        <template #default="{ row }">
          <el-tag :type="row.success ? 'success' : 'danger'" size="small">{{ row.success ? '成功' : '失败' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="参数预览" min-width="200" show-overflow-tooltip>
        <template #default="{ row }">
          <span class="admin-results-page__mono">{{ row.parameters_preview || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="失败原因" min-width="180" show-overflow-tooltip>
        <template #default="{ row }">
          <span v-if="!row.success" class="admin-results-page__error-preview">{{ row.error_preview || '-' }}</span>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column label="时间" width="170">
        <template #default="{ row }">
          <span class="admin-results-page__mono">{{ formatDateTime(row.timestamp) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="150" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="viewResult(row.id)">查看</el-button>
          <el-button link type="info" @click="goTaskDetail(row)">任务</el-button>
          <el-button link type="danger" @click="handleDelete(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </DataTableCard>

    <el-drawer v-model="drawerVisible" title="结果详情" :size="isMobile ? '100%' : '620px'">
      <div v-if="currentResult" class="result-drawer">
        <section class="result-section">
          <el-descriptions :column="2" size="small" border>
            <el-descriptions-item label="结果 ID">{{ currentResult.id }}</el-descriptions-item>
            <el-descriptions-item label="步骤索引">{{ currentResult.step_index ?? '-' }}</el-descriptions-item>
            <el-descriptions-item label="状态">
              <el-tag :type="currentResult.success ? 'success' : 'danger'" size="small">{{ currentResult.success ? '成功' : '失败' }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="时间">{{ formatDateTime(currentResult.timestamp) }}</el-descriptions-item>
            <el-descriptions-item label="任务" :span="2">
              <span class="admin-results-page__mono">{{ currentResult.task_id }}</span>
            </el-descriptions-item>
          </el-descriptions>
          <div class="result-section__actions">
            <el-button size="small" type="primary" plain @click="jumpToTask">跳转任务详情</el-button>
          </div>
        </section>
        <section class="result-section">
          <div class="result-section__head">
            <h4 class="section-label">参数信息</h4>
            <el-button size="small" @click="copyJson(currentResult.parameters, '参数 JSON')">复制参数</el-button>
          </div>
          <pre class="mono-pre result-block result-block--limited">{{ prettyJson(currentResult.parameters) }}</pre>
        </section>
        <section class="result-section">
          <div class="result-section__head">
            <h4 class="section-label">执行结果</h4>
            <el-button size="small" @click="copyJson(currentResult.result, '结果 JSON')">复制结果</el-button>
          </div>
          <pre class="mono-pre result-block result-block--limited">{{ prettyJson(currentResult.result) }}</pre>
        </section>
        <section v-if="currentResult.error_message" class="result-section">
          <h4 class="section-label">错误信息</h4>
          <pre class="mono-pre mono-pre--danger result-block">{{ currentResult.error_message }}</pre>
        </section>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, reactive, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getResults, getResult, deleteResult } from '@/api/template'
import { formatDateTime } from '@/utils/format'
import { taskDetailRoute, taskTypeLabel } from '@/utils/task_meta'
import { useResponsive } from '@/composables/useResponsive'
import PageToolbar from '@/components/PageToolbar.vue'
import FilterToolbar from '@/components/FilterToolbar.vue'
import DataTableCard from '@/components/DataTableCard.vue'

const route = useRoute()
const router = useRouter()
const { isMobile } = useResponsive()
const results = ref([])
const loading = ref(false)
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const summary = reactive({ success: 0, failed: 0 })
// ref 而非 reactive：FilterToolbar 的 v-model 会整体替换对象
const filters = ref({ keyword: '', success: '' })
const drawerVisible = ref(false)
const currentResult = ref(null)

const filterDefs = [
  {
    key: 'success',
    type: 'select',
    placeholder: '状态',
    span: { xs: 24, sm: 6, md: 4 },
    options: [
      { value: 'success', label: '成功' },
      { value: 'failed', label: '失败' },
    ],
  },
  {
    key: 'keyword',
    type: 'input',
    placeholder: '任务名称 / 任务 ID（支持部分匹配）',
    span: { xs: 24, sm: 12, md: 8 },
  },
]

async function loadResults() {
  loading.value = true
  try {
    const params = { page: page.value, per_page: pageSize.value }
    if (filters.value.success === 'success') params.success = true
    if (filters.value.success === 'failed') params.success = false
    if (filters.value.keyword) params.keyword = filters.value.keyword
    const res = await getResults(params)
    results.value = res.items || []
    total.value = res.total || 0
    summary.success = res.total_success ?? 0
    summary.failed = res.total_failed ?? 0
  } finally {
    loading.value = false
  }
}

function doFilter() {
  page.value = 1
  loadResults()
  syncUrl()
}

function clearFilters() {
  filters.value = { keyword: '', success: '' }
  doFilter()
}

// ── URL 状态同步：筛选/页码写 query，刷新与前进后退可恢复；兼容旧 task_id 链接（归一为 keyword）──

function syncUrl() {
  const query = {}
  if (page.value > 1) query.page = String(page.value)
  if (filters.value.success) query.success = filters.value.success
  if (filters.value.keyword) query.keyword = filters.value.keyword
  router.replace({ query })
}

function loadStateFromUrl() {
  const p = parseInt(route.query.page, 10)
  if (!Number.isNaN(p) && p > 0) page.value = p
  const success = ['success', 'failed'].includes(route.query.success) ? route.query.success : ''
  const keyword = String(route.query.keyword || route.query.task_id || '')
  filters.value = { keyword, success }
}

watch(
  () => route.query,
  (q) => {
    const p = parseInt(q.page, 10)
    const targetPage = !Number.isNaN(p) && p > 0 ? p : 1
    const targetKeyword = String(q.keyword || q.task_id || '')
    const targetSuccess = ['success', 'failed'].includes(q.success) ? q.success : ''
    if (targetPage === page.value && targetKeyword === filters.value.keyword && targetSuccess === filters.value.success) return
    page.value = targetPage
    filters.value = { keyword: targetKeyword, success: targetSuccess }
    loadResults()
  }
)

function shortTaskId(id) {
  if (!id) return '-'
  return id.length > 10 ? `${id.slice(0, 10)}…` : id
}

function prettyJson(value) {
  if (value == null || value === '') return '-'
  try {
    return JSON.stringify(typeof value === 'string' ? JSON.parse(value) : value, null, 2)
  } catch {
    return String(value)
  }
}

async function viewResult(id) {
  try {
    const res = await getResult(id)
    currentResult.value = res
    drawerVisible.value = true
  } catch {
    ElMessage.error('加载结果详情失败')
  }
}

function goTaskDetail(row) {
  if (!row?.task_id) return
  router.push(taskDetailRoute({ id: row.task_id, task_type: row.task_type }))
}

// 抽屉内按任务类型分流跳转（result 详情带 task_type）
function jumpToTask() {
  if (!currentResult.value?.task_id) return
  router.push(taskDetailRoute({
    id: currentResult.value.task_id,
    task_type: currentResult.value.task_type,
  }))
}

async function copyJson(value, label) {
  try {
    await navigator.clipboard.writeText(prettyJson(value))
    ElMessage.success(`已复制${label}`)
  } catch {
    ElMessage.error('复制失败')
  }
}

async function handleDelete(id) {
  await ElMessageBox.confirm('确定要删除这条结果记录吗？', '确认删除', { type: 'warning' })
  await deleteResult(id)
  ElMessage.success('删除成功')
  loadResults()
}

onMounted(() => {
  loadStateFromUrl()
  loadResults()
})
</script>

<style scoped>
.admin-results-page__summary {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  font-size: var(--app-font-sm);
  color: var(--app-text-muted);
}

.admin-results-page__summary-success {
  color: #16a34a;
}

.admin-results-page__summary-failed {
  color: #ef4444;
}

.admin-results-page__task-name {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.admin-results-page__task-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 3px;
}

.admin-results-page__task-id {
  font-size: var(--app-font-xs);
  color: var(--app-text-muted);
  font-family: 'Fira Code', monospace;
  cursor: help;
}

.admin-results-page__mono {
  font-family: 'Fira Code', monospace;
  font-size: 12px;
}

.admin-results-page__error-preview {
  color: #dc2626;
  font-size: 12px;
}

.result-drawer {
  display: grid;
  gap: 18px;
}

.result-section {
  display: grid;
  gap: 10px;
}

.result-section__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.result-section__actions {
  display: flex;
  justify-content: flex-end;
}

.result-block {
  max-height: 300px;
}

.result-block--limited {
  max-height: 300px;
}
</style>
