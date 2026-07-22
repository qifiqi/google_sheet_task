<script setup lang="ts">
import { onMounted, reactive, shallowRef } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import ResultDetailDialog from '../../components/tasks/ResultDetailDialog.vue'
import ResultListTable from '../../components/tasks/ResultListTable.vue'
import { requestJson } from '../../api/http'
import { useAuth } from '../../composables/useAuth'
import type { TaskResultDetail, TaskResultItem, TaskResultListResponse } from '../../types/api'

const auth = useAuth()
const items = shallowRef<TaskResultItem[]>([])
const loading = shallowRef(false)
const errorMessage = shallowRef('')
const detailVisible = shallowRef(false)
const selectedResult = shallowRef<TaskResultDetail | null>(null)
const filters = reactive({ taskId: '' })
const pagination = reactive({ page: 1, perPage: 20, total: 0, pages: 0 })

function canDelete() {
  return auth.hasPermission('task:delete')
}

async function loadResults(page = pagination.page) {
  loading.value = true
  errorMessage.value = ''
  const params = new URLSearchParams({ page: String(page), per_page: String(pagination.perPage) })
  if (filters.taskId.trim()) params.set('task_id', filters.taskId.trim())

  try {
    const data = await requestJson<TaskResultListResponse>(`/api/results?${params}`)
    items.value = data.results
    Object.assign(pagination, { page: data.current_page, total: data.total, pages: data.pages })
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '加载结果失败'
  } finally {
    loading.value = false
  }
}

function search() {
  loadResults(1)
}

function reset() {
  filters.taskId = ''
  loadResults(1)
}

async function openDetail(item: TaskResultItem) {
  detailVisible.value = true
  selectedResult.value = null
  try {
    selectedResult.value = await requestJson<TaskResultDetail>(`/api/results/${item.id}`)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '加载结果详情失败')
  }
}

async function removeResult(item: TaskResultItem) {
  await ElMessageBox.confirm(`确定删除结果 #${item.id} 吗？`, '删除结果', {
    type: 'error',
    confirmButtonText: '删除',
  })
  await requestJson(`/api/results/${item.id}`, { method: 'DELETE' })
  ElMessage.success('结果已删除')
  loadResults(items.value.length === 1 && pagination.page > 1 ? pagination.page - 1 : pagination.page)
}

onMounted(loadResults)
</script>

<template>
  <section class="result-page">
    <header class="result-page__header">
      <div>
        <p>任务模块</p>
        <h1>任务结果</h1>
      </div>
      <span>按任务与参数组合查看执行产出</span>
    </header>

    <section class="result-page__panel">
      <div class="result-page__toolbar">
        <el-input v-model="filters.taskId" clearable placeholder="按任务 ID 筛选" @keyup.enter="search" />
        <el-button type="primary" @click="search">查询</el-button>
        <el-button @click="reset">重置</el-button>
        <el-button text :icon="Refresh" aria-label="刷新结果列表" @click="() => loadResults()" />
      </div>
      <el-alert v-if="errorMessage" :title="errorMessage" type="error" show-icon :closable="false" />
      <ResultListTable :items="items" :loading="loading" :can-delete="canDelete()" @view="openDetail" @remove="removeResult" />
      <footer class="result-page__pagination">
        <span>共 {{ pagination.total }} 条</span>
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.perPage"
          background
          layout="total, sizes, prev, pager, next"
          :page-sizes="[20, 50, 100]"
          :total="pagination.total"
          @current-change="loadResults"
          @size-change="() => loadResults(1)"
        />
      </footer>
    </section>
    <ResultDetailDialog v-model="detailVisible" :result="selectedResult" />
  </section>
</template>

<style scoped>
.result-page { display: grid; gap: 16px; }
.result-page__header { display: flex; align-items: end; justify-content: space-between; gap: 16px; }
.result-page__header p { margin: 0 0 2px; color: var(--admin-text-muted); font-size: 13px; }
.result-page__header h1 { margin: 0; color: var(--admin-text); font-size: 20px; font-weight: 600; }
.result-page__header > span { color: var(--admin-text-muted); font-size: 13px; }
.result-page__panel { display: grid; gap: 16px; padding: 16px 20px; border: 1px solid var(--admin-border); border-radius: var(--admin-radius); background: var(--admin-surface); }
.result-page__toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.result-page__toolbar :deep(.el-input) { width: 280px; }
.result-page__pagination { display: flex; align-items: center; justify-content: space-between; gap: 12px; color: var(--admin-text-muted); font-size: 13px; }
@media (max-width: 640px) { .result-page__header, .result-page__pagination { align-items: start; flex-direction: column; }.result-page__header { gap: 4px; }.result-page__toolbar :deep(.el-input) { width: 100%; }.result-page__pagination :deep(.el-pagination) { flex-wrap: wrap; } }
</style>
