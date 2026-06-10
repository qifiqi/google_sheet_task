<template>
  <div class="global-preview-page" v-loading="loading">
    <PageToolbar eyebrow="回测训练" title="全局预览">
      <template #actions>
        <el-button type="primary" plain @click="handleExport" :loading="exporting">
          <el-icon style="margin-right: 4px"><Download /></el-icon>导出 Excel
        </el-button>
        <el-button plain @click="router.push(`/backtest/${taskId}`)">返回详情</el-button>
      </template>
    </PageToolbar>

    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>聚合数据</span>
          <el-button size="small" @click="loadPreview">
            <el-icon><Refresh /></el-icon> 刷新
          </el-button>
        </div>
      </template>

      <el-table
        :data="rows"
        stripe
        style="width: 100%"
        max-height="650"
        :show-summary="rows.length > 0"
        :summary-method="getSummary"
      >
        <el-table-column
          v-for="col in columns"
          :key="col.prop"
          :prop="col.prop"
          :label="col.label"
          :width="col.width"
          :min-width="col.minWidth"
          sortable
          show-overflow-tooltip
        />
      </el-table>

      <EmptyState v-if="!loading && rows.length === 0" description="暂无预览数据" />
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Download, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { getGlobalPreview, exportGlobalPreview } from '@/api/backtest'
import PageToolbar from '@/components/PageToolbar.vue'
import EmptyState from '@/components/EmptyState.vue'

const route = useRoute()
const router = useRouter()
const taskId = computed(() => route.params.id)

const loading = ref(false)
const exporting = ref(false)
const previewData = ref(null)

const rows = computed(() => {
  if (!previewData.value) return []
  return previewData.value.rows || previewData.value.data || previewData.value || []
})

const columns = computed(() => {
  const r = rows.value
  if (!r.length) return []
  return Object.keys(r[0]).map(key => ({
    prop: key,
    label: key,
    minWidth: 120,
  }))
})

function getSummary({ columns: cols, data }) {
  const sums = []
  cols.forEach((col, index) => {
    if (index === 0) {
      sums[index] = '合计'
      return
    }
    const values = data.map(item => Number(item[col.property]))
    if (values.every(v => !isNaN(v))) {
      const total = values.reduce((a, b) => a + b, 0)
      sums[index] = total.toFixed(2)
    } else {
      sums[index] = '-'
    }
  })
  return sums
}

async function loadPreview() {
  loading.value = true
  try {
    const res = await getGlobalPreview(taskId.value)
    previewData.value = res.data || res
  } catch {
    previewData.value = null
    ElMessage.error('加载预览数据失败')
  } finally {
    loading.value = false
  }
}

async function handleExport() {
  exporting.value = true
  try {
    const res = await exportGlobalPreview(taskId.value)
    const blob = new Blob([res], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `backtest_global_preview_${taskId.value}.xlsx`
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('导出成功')
  } catch {
    ElMessage.error('导出失败')
  } finally {
    exporting.value = false
  }
}

onMounted(loadPreview)
</script>

<style lang="scss" scoped>
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
</style>
