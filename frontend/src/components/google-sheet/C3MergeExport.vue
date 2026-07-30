<script setup lang="ts">
import { useRouter } from 'vue-router'
import { ArrowLeft, Download, Refresh, Search } from '@element-plus/icons-vue'
import C3MergeExportTable from './C3MergeExportTable.vue'
import { C3_MERGE_EXPORT_LIMIT, useC3MergeExport } from '../../composables/useC3MergeExport'

const router = useRouter()
const {
  filters,
  items,
  pagination,
  selectedTasks,
  selectedIds,
  selectedCount,
  loading,
  exporting,
  errorMessage,
  allCurrentPageSelected,
  hasSelectedOnCurrentPage,
  toggleTask,
  selectCurrentPage,
  deselectCurrentPage,
  invertCurrentPage,
  clearSelection,
  applyFilters,
  resetFilters,
  setPage,
  setPageSize,
  refreshTasks,
  exportSelected,
} = useC3MergeExport()

function returnToList() {
  void router.push({ name: 'C3Tasks' })
}
</script>

<template>
  <section class="c3-merge-export">
    <header class="c3-merge-export__header">
      <div>
        <p>业务模块 / Google Sheet C3</p>
        <h1>合并导出</h1>
      </div>
      <el-button :icon="ArrowLeft" @click="returnToList">返回任务列表</el-button>
    </header>

    <section class="c3-merge-export__selection" aria-label="已选任务">
      <div class="c3-merge-export__selection-header">
        <div>
          <h2>已选任务</h2>
          <p>将多个 C3 任务结果合并为一个 CSV 文件。</p>
        </div>
        <div class="c3-merge-export__selection-actions">
          <span><strong>{{ selectedCount }}</strong> / {{ C3_MERGE_EXPORT_LIMIT }}</span>
          <el-button type="primary" :icon="Download" :loading="exporting" :disabled="selectedCount === 0" @click="exportSelected">导出选中任务</el-button>
        </div>
      </div>
      <div v-if="selectedTasks.length" class="c3-merge-export__selected-list">
        <el-tag v-for="task in selectedTasks" :key="task.id" closable effect="plain" @close="toggleTask(task, false)">{{ task.name }}</el-tag>
      </div>
      <p v-else class="c3-merge-export__selection-empty">暂未选择任务</p>
    </section>

    <section class="c3-merge-export__table-panel">
      <header class="c3-merge-export__table-header">
        <div>
          <h2>C3 任务</h2>
          <p>共 {{ pagination.total }} 个匹配任务，跨页选择会保留。</p>
        </div>
      </header>

      <div class="c3-merge-export__filters">
        <el-input v-model="filters.keyword" clearable :prefix-icon="Search" aria-label="搜索任务名称" placeholder="搜索任务名称" @keyup.enter="applyFilters" />
      <el-select v-model="filters.status" clearable persistent popper-class="c-series-fast-select" aria-label="筛选任务状态" placeholder="全部状态">
          <el-option label="待执行" value="pending" />
          <el-option label="执行中" value="running" />
          <el-option label="已完成" value="completed" />
          <el-option label="执行出错" value="error" />
          <el-option label="已取消" value="cancelled" />
        </el-select>
        <el-button type="primary" @click="applyFilters">查询</el-button>
        <el-button @click="resetFilters">重置</el-button>
        <el-button text :icon="Refresh" aria-label="刷新任务列表" @click="refreshTasks" />
      </div>

      <div class="c3-merge-export__bulk-actions">
        <el-button-group>
          <el-button :disabled="allCurrentPageSelected || selectedCount >= C3_MERGE_EXPORT_LIMIT" @click="selectCurrentPage">选择当页</el-button>
          <el-button @click="invertCurrentPage">反选当页</el-button>
          <el-button :disabled="!hasSelectedOnCurrentPage" @click="deselectCurrentPage">取消当页</el-button>
        </el-button-group>
        <el-button :disabled="selectedCount === 0" @click="clearSelection">清空选择</el-button>
        <span>最多选择 {{ C3_MERGE_EXPORT_LIMIT }} 个任务</span>
      </div>

      <el-alert v-if="errorMessage" :title="errorMessage" type="error" show-icon :closable="false" />
      <C3MergeExportTable
        :items="items"
        :loading="loading"
        :selected-ids="selectedIds"
        :selected-count="selectedCount"
        :max-selection="C3_MERGE_EXPORT_LIMIT"
        @toggle="toggleTask"
      />

      <footer class="c3-merge-export__pagination">
        <span>共 {{ pagination.total }} 条</span>
        <el-pagination
          :current-page="pagination.page"
          :page-size="pagination.per_page"
          background
          layout="total, sizes, prev, pager, next, jumper"
          :page-sizes="[10, 20, 50]"
          :total="pagination.total"
          @current-change="setPage"
          @size-change="setPageSize"
        />
      </footer>
    </section>
  </section>
</template>

<style scoped>
.c3-merge-export { display: grid; max-width: 1440px; gap: 16px; margin: 0 auto; }
.c3-merge-export__header,
.c3-merge-export__selection-header,
.c3-merge-export__table-header,
.c3-merge-export__pagination { display: flex; align-items: end; justify-content: space-between; gap: 16px; }
.c3-merge-export__header h1,
.c3-merge-export__selection h2,
.c3-merge-export__table-panel h2 { margin: 2px 0 0; color: var(--admin-text); font-weight: 600; }
.c3-merge-export__header h1 { font-size: 20px; line-height: 28px; }
.c3-merge-export__selection h2,
.c3-merge-export__table-panel h2 { font-size: 16px; line-height: 24px; }
.c3-merge-export__header p,
.c3-merge-export__selection p,
.c3-merge-export__table-panel p { margin: 0; color: var(--admin-text-muted); font-size: 13px; }
.c3-merge-export__selection,
.c3-merge-export__table-panel { border: 1px solid var(--admin-border); border-radius: var(--admin-radius); background: var(--admin-surface); }
.c3-merge-export__selection { display: grid; gap: 14px; padding: 20px; }
.c3-merge-export__selection-actions,
.c3-merge-export__filters,
.c3-merge-export__bulk-actions,
.c3-merge-export__selected-list { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
.c3-merge-export__selection-actions span { color: var(--admin-text-muted); font-size: 13px; }
.c3-merge-export__selection-actions strong { color: var(--admin-primary); font-size: 20px; font-weight: 600; }
.c3-merge-export__selected-list :deep(.el-tag) { max-width: 260px; }
.c3-merge-export__selection-empty { padding: 8px 0; }
.c3-merge-export__table-panel { display: grid; gap: 16px; padding: 16px 20px; }
.c3-merge-export__filters :deep(.el-input) { width: 240px; }
.c3-merge-export__filters :deep(.el-select) { width: 180px; }
.c3-merge-export__bulk-actions { padding-top: 12px; border-top: 1px solid var(--admin-border-light); }
.c3-merge-export__bulk-actions span { margin-left: auto; color: var(--admin-text-muted); font-size: 13px; }
.c3-merge-export__pagination { color: var(--admin-text-muted); font-size: 13px; }

@media (max-width: 760px) {
  .c3-merge-export__header,
  .c3-merge-export__selection-header,
  .c3-merge-export__pagination { align-items: stretch; flex-direction: column; }
  .c3-merge-export__selection-actions { justify-content: space-between; }
  .c3-merge-export__filters :deep(.el-input),
  .c3-merge-export__filters :deep(.el-select) { width: 100%; }
  .c3-merge-export__bulk-actions span { width: 100%; margin-left: 0; }
  .c3-merge-export__pagination :deep(.el-pagination) { flex-wrap: wrap; }
}

@media (max-width: 560px) {
  .c3-merge-export__selection,
  .c3-merge-export__table-panel { padding: 16px; }
  .c3-merge-export__selection-actions { align-items: stretch; flex-direction: column; }
  .c3-merge-export__selection-actions :deep(.el-button) { width: 100%; }
  .c3-merge-export__bulk-actions :deep(.el-button-group) { display: grid; width: 100%; grid-template-columns: repeat(3, 1fr); }
}
</style>
