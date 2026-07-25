<script setup lang="ts">
import { computed, shallowRef } from 'vue'
import { useClipboard } from '@vueuse/core'
import { DataAnalysis } from '@element-plus/icons-vue'
import VueJsonPretty from 'vue-json-pretty'
import 'vue-json-pretty/lib/styles.css'
import type { AnalysisRecord } from '../../types/analysis'
import { buildAnalysisDetails, formatDetailValue } from '../../utils/analysis-details'
import '../../styles/analysis/analysis-detail-tabs.css'

const props = defineProps<{ result?: AnalysisRecord }>()
const detailOpen = shallowRef<string[]>([])
const activeTab = shallowRef('annual')
const { copy, copied, isSupported } = useClipboard()
const sections = computed(() => buildAnalysisDetails(props.result))
const rawJson = computed(() => props.result || { status: '等待分析' })
const rawText = computed(() => JSON.stringify(rawJson.value, null, 2))

async function copyRawJson() {
  if (isSupported.value) await copy(rawText.value)
}
</script>

<template>
  <section class="analysis-detail-tabs">
    <el-collapse v-model="detailOpen">
      <el-collapse-item name="v1-details">
        <template #title>
          <div class="analysis-detail-tabs__title"><el-icon><DataAnalysis /></el-icon><strong>V1 数据明细</strong><span>按指标查看完整回测数据</span></div>
        </template>
        <el-tabs v-model="activeTab" tab-position="left">
          <el-tab-pane v-for="section in sections" :key="section.name" :label="section.label" :name="section.name">
            <el-table :data="section.rows" class="analysis-detail-tabs__table" empty-text="该指标暂无数据">
              <el-table-column v-for="column in section.columns" :key="column.key" :label="column.label" :min-width="column.minWidth" show-overflow-tooltip>
                <template #default="{ row }">{{ formatDetailValue(row[column.key], column.key === 'value' && row.format ? row.format : column.format) }}</template>
              </el-table-column>
            </el-table>
          </el-tab-pane>
          <el-tab-pane label="全量 JSON" name="raw">
            <div class="analysis-detail-tabs__raw-actions"><el-button text type="primary" :disabled="!isSupported" @click="copyRawJson">{{ copied ? '已复制' : '复制 JSON' }}</el-button></div>
            <div class="analysis-detail-tabs__json"><VueJsonPretty :data="rawJson" :deep="2" show-line-number show-length /></div>
          </el-tab-pane>
        </el-tabs>
      </el-collapse-item>
    </el-collapse>
  </section>
</template>
