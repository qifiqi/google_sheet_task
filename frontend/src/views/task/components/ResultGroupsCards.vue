<template>
  <div class="version-result-groups">
    <div v-if="!groups.length" class="panel-note panel-note--center">暂无执行结果</div>

    <!-- 按参数组合分组的模型结果卡片（对齐静态版 renderResults 的卡片视图） -->
    <el-card
      v-for="(group, gIdx) in groups"
      :key="group.rowId != null ? group.rowId : gIdx"
      shadow="never"
      class="version-result-groups__card"
    >
      <template #header>
        <div class="control-row">
          <span class="panel-note">
            股票代码：<b>{{ group.stockCode }}</b>
            <span> · K线区间：{{ group.klineRange }}</span>
            <span> · 步骤 {{ (group.stepIndex || 0) + 1 }}</span>
            <template v-if="version !== 'c4'">
              <span> · A1：{{ group.a1 != null ? group.a1 : '-' }}</span>
              <span> · B1：{{ group.b1 != null ? group.b1 : '-' }}</span>
            </template>
            <span> · 执行时间：{{ groupTime(group.timestamp) }}</span>
          </span>
          <span class="control-row">
            <el-tag :type="group.success ? 'success' : 'danger'" size="small">
              {{ group.success ? '成功' : '失败' }}
            </el-tag>
            <span class="panel-note">ID: {{ group.rowId != null ? group.rowId : '-' }}</span>
          </span>
        </div>
      </template>

      <el-table :data="group.models" size="small" border>
        <el-table-column label="模型标题" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">{{ row.modelTitle || row.modelKey }}</template>
        </el-table-column>
        <el-table-column
          v-for="col in metricColumns"
          :key="col.key"
          :label="col.label"
          width="110"
          align="center"
        >
          <template #default="{ row }">
            {{ formatMetricText(row.displayValues[col.key], 6, col.key) }}
          </template>
        </el-table-column>
        <el-table-column label="指数夏普" width="110" align="center">
          <template #default="{ row }">{{ formatSharpeText(row.indexSharpe) }}</template>
        </el-table-column>
        <el-table-column label="模型夏普" width="110" align="center">
          <template #default="{ row }">{{ formatSharpeText(row.startSharpe) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="70" align="center">
          <template #default="{ row }">
            <el-button link type="primary" @click="openModelDetail(group, row)">更多</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="group.errorMessage" class="panel-note version-result-groups__error">
        错误：{{ group.errorMessage }}
      </div>
    </el-card>

    <!-- 模型结果详情弹窗（对齐静态版 resultDetailModal：收益分析卡 + 两列指标表） -->
    <el-dialog v-model="detailVisible" :title="detailTitle" width="760px" append-to-body>
      <div class="panel-note">{{ detailMeta }}</div>

      <el-row v-if="detailStartReturn || detailIndexReturn" :gutter="12" class="version-result-groups__return-row">
        <el-col v-if="detailStartReturn" :span="12">
          <div class="sub-card">
            <div class="version-result-groups__block-title">模型收益分析</div>
            <div
              v-for="line in returnCardLines(detailStartReturn)"
              :key="line.label"
              class="version-result-groups__stat-line"
            >
              <span class="panel-note">{{ line.label }}</span>
              <span>{{ line.value }}</span>
            </div>
          </div>
        </el-col>
        <el-col v-if="detailIndexReturn" :span="12">
          <div class="sub-card">
            <div class="version-result-groups__block-title">指数收益分析</div>
            <div
              v-for="line in returnCardLines(detailIndexReturn)"
              :key="line.label"
              class="version-result-groups__stat-line"
            >
              <span class="panel-note">{{ line.label }}</span>
              <span>{{ line.value }}</span>
            </div>
          </div>
        </el-col>
      </el-row>

      <el-table v-if="detailRows.length" :data="detailRows" size="small" border class="version-result-groups__detail-table">
        <el-table-column label="指标" width="180">
          <template #default="{ row }">{{ row.label1 }}</template>
        </el-table-column>
        <el-table-column label="值">
          <template #default="{ row }">
            <template v-if="row.isObject1">
              <el-descriptions :column="1" size="small" border>
                <el-descriptions-item
                  v-for="child in row.childRows1"
                  :key="child.label"
                  :label="child.label"
                >
                  {{ child.value }}
                </el-descriptions-item>
              </el-descriptions>
            </template>
            <template v-else-if="row.isArray1">
              <pre class="version-result-groups__pre">{{ JSON.stringify(row.value1, null, 2) }}</pre>
            </template>
            <template v-else>{{ row.value1 }}</template>
          </template>
        </el-table-column>
        <el-table-column label="指标" width="180">
          <template #default="{ row }">{{ row.label2 }}</template>
        </el-table-column>
        <el-table-column label="值">
          <template #default="{ row }">
            <template v-if="row.has2">
              <template v-if="row.isObject2">
                <el-descriptions :column="1" size="small" border>
                  <el-descriptions-item
                    v-for="child in row.childRows2"
                    :key="child.label"
                    :label="child.label"
                  >
                    {{ child.value }}
                  </el-descriptions-item>
                </el-descriptions>
              </template>
              <pre v-else-if="row.isArray2" class="version-result-groups__pre">{{ JSON.stringify(row.value2, null, 2) }}</pre>
              <template v-else>{{ row.value2 }}</template>
            </template>
          </template>
        </el-table-column>
      </el-table>
      <div v-else class="panel-note panel-note--center">无详细指标</div>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import {
  buildVersionResultGroups,
  formatMetricText,
  formatSharpeText,
  getMetricDisplayLabel,
  getFlatResult,
  isPlainObject,
  shouldShowDetailMetric,
  sortMetricKeys,
  VERSION_METRIC_COLUMNS
} from './versionShared'
import { formatDateTime } from '@/utils/format'

const props = defineProps({
  // 版本标识：'c4' | 'c5' | 'c7'
  version: { type: String, required: true },
  // 当前页原始结果（服务端分页返回的 items）
  results: { type: Array, default: () => [] },
  // 解析后的任务配置（C7.0.3 取数位适配依赖 sheets[].c7_model_version）
  taskConfig: { type: Object, default: () => ({}) }
})

const metricColumns = computed(() => VERSION_METRIC_COLUMNS[props.version] || VERSION_METRIC_COLUMNS.c4)
const groups = computed(() => buildVersionResultGroups(props.version, props.results, props.taskConfig))

function groupTime(timestamp) {
  return timestamp ? formatDateTime(timestamp) : '-'
}

// ── 模型结果详情弹窗（对齐静态版 showResultDetail）──

const detailVisible = ref(false)
const detailGroup = ref(null)
const detailModel = ref(null)

const detailTitle = computed(() => {
  const model = detailModel.value
  if (!model) return '结果详情'
  return model.modelTitle && model.modelTitle.length > 0 ? model.modelTitle : (model.modelKey || '')
})

const detailMeta = computed(() => {
  const group = detailGroup.value
  if (!group) return ''
  const parts = [
    `股票代码：${group.stockCode || '-'}`,
    `K线区间：${group.klineRange || '-'}`,
    `步骤 ${(group.stepIndex || 0) + 1}`
  ]
  if (props.version !== 'c4') {
    parts.push(`A1：${group.a1 != null ? group.a1 : '-'}`)
    parts.push(`B1：${group.b1 != null ? group.b1 : '-'}`)
  }
  parts.push(`执行时间：${groupTime(group.timestamp)}`)
  return parts.join(' · ')
})

const detailMetrics = computed(() => {
  const metrics = detailModel.value?.rawMetrics
  return isPlainObject(metrics) ? metrics : {}
})

const hasFlatResult = computed(() => !!getFlatResult(detailMetrics.value))

const detailStartReturn = computed(() =>
  hasFlatResult.value ? null : (detailMetrics.value.start_return_xpl || null)
)

const detailIndexReturn = computed(() =>
  hasFlatResult.value ? null : (detailMetrics.value.index_return_xpl || null)
)

// 剩余字段进入通用两列表格（剔除字典字段），并按 D* 优先排序（老 detail 弹窗口径）
const detailRows = computed(() => {
  const metrics = detailMetrics.value
  if (!isPlainObject(metrics)) return []
  const keys = sortMetricKeys(Object.keys(metrics).filter(shouldShowDetailMetric))
  const rows = []
  for (let i = 0; i < keys.length; i += 2) {
    const k1 = keys[i]
    const k2 = keys[i + 1]
    rows.push({
      ...buildMetricCell(k1, metrics[k1], false),
      ...(k2 != null
        ? { has2: true, ...buildMetricCell(k2, metrics[k2], true) }
        : { has2: false })
    })
  }
  return rows
})

function buildMetricCell(key, value, isSecond) {
  const prefix = isSecond ? '2' : '1'
  const isObject = isPlainObject(value)
  const isArray = Array.isArray(value)
  // 百分比归一仅 C7 需要（老版 c4/c5 的 formatMetricText 不传 key）
  const metricKey = props.version === 'c7' ? key : null
  const cell = {
    [`key${prefix}`]: key,
    [`label${prefix}`]: getMetricDisplayLabel(key, props.version),
    [`value${prefix}`]: isObject || isArray ? value : formatMetricText(value, 6, metricKey),
    [`isObject${prefix}`]: isObject,
    [`isArray${prefix}`]: isArray
  }
  if (isObject) {
    // 嵌套对象渲染一层 label/value 行（老 formatMetricDisplayValue 的嵌套行口径）
    cell[`childRows${prefix}`] = sortMetricKeys(Object.keys(value).filter(shouldShowDetailMetric)).map((childKey) => ({
      label: getMetricDisplayLabel(childKey, props.version),
      value: isPlainObject(value[childKey]) || Array.isArray(value[childKey])
        ? JSON.stringify(value[childKey])
        : formatMetricText(value[childKey], 6, props.version === 'c7' ? childKey : null)
    }))
  }
  return cell
}

function openModelDetail(group, model) {
  detailGroup.value = group
  detailModel.value = model
  detailVisible.value = true
}

// 收益分析卡行（对齐静态版 renderStatLine 字段）
function returnCardLines(source) {
  if (!isPlainObject(source)) return []
  return [
    { label: '起始日期', value: source.start_date ?? '-' },
    { label: '结束日期', value: source.end_date ?? '-' },
    { label: '月份数', value: source.month_count ?? '-' },
    { label: '平均月收益', value: formatMetricText(source.avg_monthly_return, 6) },
    { label: '月度波动率', value: formatMetricText(source.monthly_std_dev, 6) },
    { label: '年化波动率', value: formatMetricText(source.annual_std_dev, 6) },
    { label: '夏普率', value: formatMetricText(source.sharpe_ratio, 6) }
  ]
}
</script>

<style scoped>
.version-result-groups__card {
  margin-bottom: 12px;
}

.version-result-groups__error {
  margin-top: 8px;
  color: var(--el-color-danger);
}

.version-result-groups__return-row {
  margin: 8px 0;
}

.version-result-groups__block-title {
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 700;
}

.version-result-groups__stat-line {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
  padding: 2px 0;
}

.version-result-groups__detail-table {
  margin-top: 8px;
}

.version-result-groups__pre {
  margin: 0;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
