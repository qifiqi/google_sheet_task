<template>
  <div class="global-preview-page" v-loading="loading">
    <PageToolbar eyebrow="多产品回测" title="全局预览">
      <template #actions>
        <el-button type="success" plain @click="openRatioDialog" :loading="calculating">
          <el-icon style="margin-right: 4px"><Setting /></el-icon>调整权重
        </el-button>
        <el-button type="primary" plain @click="handleExport" :loading="exporting">
          <el-icon style="margin-right: 4px"><Download /></el-icon>导出 Excel
        </el-button>
        <el-button plain @click="router.push(`/backtest-multi/${taskId}`)">返回详情</el-button>
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

    <!-- Ratio Adjustment Dialog -->
    <el-dialog v-model="ratioDialogVisible" title="权重调整" width="520px" destroy-on-close>
      <el-form label-width="120px" label-position="top">
        <el-form-item
          v-for="(item, index) in ratioItems"
          :key="index"
          :label="item.label || `产品 ${index + 1}`"
        >
          <el-input-number
            v-model="item.ratio"
            :min="0"
            :max="1"
            :step="0.01"
            :precision="2"
            style="width: 100%"
          />
        </el-form-item>
        <div class="ratio-total">
          权重合计：<strong :class="{ 'ratio-total--warn': ratioTotal > 1.01 || ratioTotal < 0.99 }">{{ ratioTotal.toFixed(2) }}</strong>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="ratioDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingRatios" @click="handleSaveRatios">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Download, Refresh, Setting } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { getGlobalPreview, exportGlobalPreview, updateRatios } from '@/api/backtestMulti'
import PageToolbar from '@/components/PageToolbar.vue'
import EmptyState from '@/components/EmptyState.vue'

const route = useRoute()
const router = useRouter()
const taskId = computed(() => route.params.id)

const loading = ref(false)
const exporting = ref(false)
const calculating = ref(false)
const savingRatios = ref(false)
const previewData = ref(null)

const ratioDialogVisible = ref(false)
const ratioItems = ref([])

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

const ratioTotal = computed(() => {
  return ratioItems.value.reduce((sum, item) => sum + (item.ratio || 0), 0)
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

function openRatioDialog() {
  // Initialise ratio items from preview data products or config
  const products = previewData.value?.products || previewData.value?.product_ratios || []
  if (Array.isArray(products) && products.length) {
    ratioItems.value = products.map(p => ({
      label: p.name || p.product_name || p.code || '产品',
      ratio: p.ratio ?? 1,
      code: p.code || p.product_code || '',
    }))
  } else {
    // Default: allow user to add items
    ratioItems.value = [
      { label: '产品 1', ratio: 1, code: '' },
    ]
  }
  ratioDialogVisible.value = true
}

async function handleSaveRatios() {
  savingRatios.value = true
  try {
    const payload = ratioItems.value.map(item => ({
      code: item.code,
      ratio: item.ratio,
    }))
    await updateRatios(taskId.value, { ratios: payload })
    ElMessage.success('权重已保存')
    ratioDialogVisible.value = false
    await loadPreview()
  } catch (err) {
    ElMessage.error(err?.response?.data?.message || '保存失败')
  } finally {
    savingRatios.value = false
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
    a.download = `backtest_multi_global_preview_${taskId.value}.xlsx`
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

.ratio-total {
  padding: 10px 0;
  font-size: 14px;
  color: var(--el-text-color-regular);

  strong {
    font-size: 16px;
    color: var(--el-color-success);
  }

  &--warn {
    color: var(--el-color-danger) !important;
  }
}
</style>
