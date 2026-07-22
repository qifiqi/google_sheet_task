<script setup lang="ts">
import { computed, onMounted, reactive, shallowRef, watch } from 'vue'
import { ArrowLeft, Download, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import GlobalPreviewTable from '../../components/analysis/GlobalPreviewTable.vue'
import MultiProductRatioPanel from '../../components/analysis/MultiProductRatioPanel.vue'
import { useGlobalPreview } from '../../composables/useGlobalPreview'
import type { AnalysisSource } from '../../types/analysis'
import { downloadFile } from '../../utils/download'
import '../../styles/analysis/global-preview-page.css'

type GlobalPreviewSource = Extract<AnalysisSource, 'backtest-training' | 'backtest-multi-product'>

const props = defineProps<{
  source: GlobalPreviewSource
  taskId: string
}>()

const router = useRouter()
const preview = useGlobalPreview(props.source, props.taskId)
const activeGroupKey = shallowRef('')
const ratioValues = reactive<number[]>([])
const isMultiProduct = computed(() => props.source === 'backtest-multi-product')
const groups = computed(() => preview.payload.value?.groups || [])
const activeGroup = computed(() => groups.value.find((group) => group.group_key === activeGroupKey.value) || groups.value[0] || null)
const summaryEntries = computed(() => Object.entries(preview.payload.value?.summary || {}))
const backPath = computed(() => props.source === 'backtest-training' ? '/backtest/training/tasks' : '/backtest/multi-product/tasks')

watch(preview.payload, (payload) => {
  activeGroupKey.value = payload?.groups?.[0]?.group_key || ''
  ratioValues.splice(0, ratioValues.length, ...(payload?.products || []).map((product) => Number(product.ratio) || 0))
}, { immediate: true })

async function load() {
  try {
    await preview.load()
  } catch {
    ElMessage.error(preview.errorMessage.value || '加载预览失败')
  }
}

async function calculateRatios() {
  try {
    await preview.calculateRatios([...ratioValues])
    ElMessage.success('比例预览已更新')
  } catch {
    ElMessage.error(preview.errorMessage.value || '比例计算失败')
  }
}

async function saveRatios() {
  try {
    await preview.saveRatios([...ratioValues])
    ElMessage.success('比例已保存')
  } catch {
    ElMessage.error(preview.errorMessage.value || '保存比例失败')
  }
}

async function exportPreview() {
  try {
    let url = preview.endpoint('/export')
    if (isMultiProduct.value) {
      url += `?ratios=${encodeURIComponent(JSON.stringify(ratioValues.map((ratio, productIndex) => ({ product_index: productIndex, ratio }))))}`
    }
    await downloadFile(url, `${props.taskId}_global_preview.xlsx`)
    ElMessage.success('已开始下载')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '导出失败')
  }
}

onMounted(load)
</script>

<template>
  <section class="global-preview-page">
    <header class="global-preview-page__header">
      <div>
        <p>数据回测</p>
        <h1>全局预览</h1>
        <span>{{ preview.payload.value?.task?.name || taskId }}</span>
      </div>
      <div class="global-preview-page__actions">
        <el-button :icon="ArrowLeft" @click="router.push(backPath)">返回列表</el-button>
        <el-button :icon="Refresh" :loading="preview.loading.value" @click="load">刷新</el-button>
        <el-button type="primary" :icon="Download" :disabled="!preview.payload.value" @click="exportPreview">导出</el-button>
      </div>
    </header>
    <el-alert v-if="preview.errorMessage.value" :title="preview.errorMessage.value" type="error" show-icon :closable="false" />
    <el-skeleton v-if="preview.loading.value && !preview.payload.value" :rows="10" animated />
    <template v-else-if="preview.payload.value">
      <section class="global-preview-page__summary">
        <div v-for="([key, value]) in summaryEntries" :key="key"><span>{{ key }}</span><strong>{{ value }}</strong></div>
      </section>
      <MultiProductRatioPanel
        v-if="isMultiProduct"
        v-model:ratios="ratioValues"
        :products="preview.payload.value.products"
        :loading="preview.loading.value"
        @preview="calculateRatios"
        @save="saveRatios"
      />
      <section class="global-preview-page__group-select">
        <el-select v-model="activeGroupKey" placeholder="选择分组">
          <el-option v-for="group in groups" :key="group.group_key" :label="group.group_label" :value="group.group_key" />
        </el-select>
      </section>
      <GlobalPreviewTable :group="activeGroup" />
    </template>
  </section>
</template>
