<template>
  <div class="app-page export-preview-page">
    <PageToolbar
      eyebrow="Backtest Result"
      title="导出内容预览"
      :description="previewFilename || '正在加载...'"
    >
      <template #actions>
        <el-button :disabled="!rows.length" @click="copyAllRows">复制全部</el-button>
        <el-button type="success" :disabled="!rows.length" :loading="downloading" @click="downloadCsv">下载 CSV</el-button>
        <el-button class="page-back-button" @click="$router.push({ path: `/backtest/${resultId}/result`, query: pagingQuery })">返回结果</el-button>
      </template>
    </PageToolbar>

    <el-card shadow="never" v-loading="loading">
      <div class="export-preview-page__status" role="status">{{ statusText }}</div>
      <div v-if="rows.length" class="export-preview-page__grid" tabindex="0">
        <table class="export-preview-page__table">
          <tbody>
            <tr v-for="(row, rowIndex) in rows" :key="rowIndex">
              <td v-for="(value, colIndex) in row" :key="colIndex">{{ value == null ? '' : value }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <el-empty v-else-if="!loading" :description="statusText || '暂无导出内容'" :image-size="80" />
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import PageToolbar from '@/components/PageToolbar.vue'
import { getTaskResultExportPreview, exportBacktestResultCsv } from '@/api/backtest'
import { pickPagingQuery } from '@/utils/pageState'

const route = useRoute()
const resultId = route.params.id
// 返回结果页时透传分页上下文（与静态版 buildResultHref 一致）
const pagingQuery = pickPagingQuery(route.query)

const loading = ref(false)
const downloading = ref(false)
const rows = ref([])
const previewFilename = ref('')
const statusText = ref('')

async function loadPreview() {
  loading.value = true
  try {
    const payload = await getTaskResultExportPreview(encodeURIComponent(resultId))
    rows.value = Array.isArray(payload.rows) ? payload.rows : []
    previewFilename.value = payload.filename || `backtest_result_${resultId}_details.csv`
    statusText.value = `已加载 ${rows.value.length} 行导出内容`
  } catch (error) {
    rows.value = []
    statusText.value = error.message || '加载失败'
  } finally {
    loading.value = false
  }
}

function buildClipboardText() {
  return rows.value
    .map((row) => row.map((value) => (value == null ? '' : String(value))).join('\t'))
    .join('\n')
}

async function copyAllRows() {
  const text = buildClipboardText()
  if (!text) {
    statusText.value = '暂无可复制内容'
    return
  }
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
    } else {
      const textarea = document.createElement('textarea')
      textarea.value = text
      textarea.setAttribute('readonly', '')
      textarea.style.position = 'fixed'
      textarea.style.left = '-9999px'
      document.body.appendChild(textarea)
      textarea.select()
      const copied = document.execCommand('copy')
      textarea.remove()
      if (!copied) throw new Error('复制失败')
    }
    statusText.value = '已复制全部内容，可直接粘贴到 WPS 或 Excel'
  } catch (error) {
    statusText.value = `复制失败：${error.message || '未知错误'}`
  }
}

async function downloadCsv() {
  downloading.value = true
  try {
    const blob = await exportBacktestResultCsv(resultId)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = previewFilename.value || `backtest_result_${resultId}.csv`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
    statusText.value = '已开始下载 CSV 文件'
  } catch (error) {
    statusText.value = `下载失败：${error.message || '未知错误'}`
  } finally {
    downloading.value = false
  }
}

onMounted(loadPreview)
</script>

<style scoped>
.export-preview-page__status {
  margin-bottom: 12px;
  font-size: var(--app-font-xs, 12px);
  color: var(--app-text-muted, #909399);
}

.export-preview-page__grid {
  overflow: auto;
  max-height: 70vh;
  border: 1px solid var(--el-border-color-lighter);
}

.export-preview-page__table {
  border-collapse: collapse;
  font-size: var(--app-font-xs, 12px);
  font-family: var(--app-font-mono, monospace);
}

.export-preview-page__table td {
  border: 1px solid var(--el-border-color-lighter);
  padding: 4px 8px;
  white-space: nowrap;
}
</style>
