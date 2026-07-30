<script setup lang="ts">
import { computed, shallowRef } from 'vue'

type Mode = 'c3' | 'c4' | 'c5' | 'c7'
type SheetConfig = Record<string, unknown>

const props = defineProps<{ config: Record<string, unknown>; mode: Mode }>()
const activeNames = shallowRef<string[]>([])

const sheets = computed<SheetConfig[]>(() => {
  if (Array.isArray(props.config.sheets)) return props.config.sheets.filter((value): value is SheetConfig => Boolean(value && typeof value === 'object'))
  const id = props.config.spreadsheet_id || props.config.spreadsheetId
  return id ? [{ spreadsheet_id: id, title: props.config.title || props.config.spreadsheet_title, sheet_name: props.config.sheet_name || props.config.sheetName }] : []
})
const parameters = computed(() => Array.isArray(props.config.parameters) ? props.config.parameters : [])
const productCodes = computed(() => props.mode === 'c4' && Array.isArray(parameters.value[0]) ? parameters.value[0].map(String) : [])
const sourceLabel = computed(() => props.config.kline_source === 'custom' ? 'Sheet 自定义 K 线' : '自动获取 K 线')
const marketLabel = computed(() => ({ cn: 'A 股', us: '美股', en: '美股', custom: '自定义' }[String(props.config.market_type)] || '-'))
const visibleSettings = computed(() => {
  const values = [{ label: '统计方式', value: props.config.count_mode === 'n_plus_1' ? 'N+1' : '总数' }]
  if (props.mode === 'c3') {
    values.unshift({ label: '标的', value: [props.config.stock_code, props.config.stock_name].filter(Boolean).join(' / ') || '-' })
    values.push({ label: '结束日期', value: String(props.config.end_date || '-') }, { label: '回溯年数', value: props.config.year_n ? `${props.config.year_n} 年` : '-' })
    return values
  }
  values.unshift({ label: 'K 线来源', value: sourceLabel.value })
  if (props.config.kline_source !== 'custom') values.push(
    { label: '价格类型', value: ({ kp_price: '开盘价', sp_price: '收盘价', vwap_price: 'VWAP' }[String(props.config.price_mode)] || '-') },
    { label: '市场类型', value: marketLabel.value },
    { label: '数据日期', value: `${props.config.start_date || '-'} 至 ${props.config.end_date || '-'}` },
  )
  return values
})
const advancedSettings = computed(() => [
  { label: 'K 线复权', value: ({ forward: '前复权', back: '后复权', none: '不复权' }[String(props.config.kline_adjustment)] || '-') },
  { label: '范围模式', value: Array.isArray(props.config.date_range_mode) ? props.config.date_range_mode.join('、') : '-' },
  { label: '排除近年', value: Array.isArray(props.config.exclude_recent_years) && props.config.exclude_recent_years.length ? props.config.exclude_recent_years.map((year) => `近 ${year} 年`).join('、') : '无' },
  { label: '认证方式', value: props.config.token_type === 'json' ? 'Token JSON' : 'Token 文件' },
  { label: '代理', value: props.config.proxy_url ? '已配置' : '未配置' },
])
function sheetTitle(sheet: SheetConfig) { return String(sheet.title || sheet.spreadsheet_title || '未命名 Sheet') }
function sheetId(sheet: SheetConfig) { return String(sheet.spreadsheet_id || sheet.spreadsheetId || '-') }
function sheetName(sheet: SheetConfig) { return String(sheet.sheet_name || sheet.sheetName || '-') }
</script>

<template>
  <div class="task-config">
    <section class="task-config__primary">
      <section class="task-config__section task-config__section--sheet">
        <header class="task-config__section-header"><h3>执行资源</h3><span>{{ sheets.length }} 个 Google Sheet</span></header>
        <el-empty v-if="!sheets.length" description="未配置 Sheet" :image-size="42" />
        <div v-else class="task-config__sheet-grid">
          <article v-for="(sheet, index) in sheets" :key="`${sheetId(sheet)}-${index}`" class="task-config__sheet">
            <el-tag type="info" effect="plain">Sheet {{ index + 1 }}</el-tag>
            <strong :title="sheetTitle(sheet)">{{ sheetTitle(sheet) }}</strong>
            <span>资源 ID：{{ sheetId(sheet) }}</span><span>工作表：{{ sheetName(sheet) }}</span>
          </article>
        </div>
      </section>

      <section class="task-config__section task-config__section--parameters">
        <header class="task-config__section-header"><h3>{{ mode === 'c4' ? '产品代码' : '参数组合' }}</h3><span>{{ mode === 'c4' ? `${productCodes.length} 个代码` : `${parameters.length} 组参数` }}</span></header>
        <el-empty v-if="mode === 'c4' && !productCodes.length" description="未配置产品代码" :image-size="42" />
        <div v-else-if="mode === 'c4'" class="task-config__chips"><el-tag v-for="code in productCodes" :key="code" type="primary" effect="light">{{ code }}</el-tag></div>
        <el-empty v-else-if="!parameters.length" description="无参数配置" :image-size="42" />
        <div v-else class="task-config__parameter-list">
          <div v-for="(group, index) in parameters" :key="index" class="task-config__parameter"><span>参数 {{ index + 1 }}：</span><code>{{ JSON.stringify(group) }}</code></div>
        </div>
      </section>
    </section>

    <el-descriptions class="task-config__settings" :column="3" border>
      <el-descriptions-item v-for="item in visibleSettings" :key="item.label" :label="item.label">{{ item.value }}</el-descriptions-item>
    </el-descriptions>
    <el-collapse v-model="activeNames" class="task-config__advanced">
      <el-collapse-item name="advanced">
        <template #title><span>更多执行设置</span><small>认证与行情选项</small></template>
        <el-descriptions :column="3" border><el-descriptions-item v-for="item in advancedSettings" :key="item.label" :label="item.label">{{ item.value }}</el-descriptions-item></el-descriptions>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<style scoped>
.task-config {
  display: grid;
  gap: 18px;
}

.task-config__primary {
  display: grid;
  grid-template-columns: minmax(0, 0.9fr) minmax(0, 1.1fr);
  align-items: stretch;
  gap: 12px;
}

.task-config__section {
  display: grid;
  align-content: start;
  gap: 10px;
  min-width: 0;
  padding: 12px;
  border: 1px solid var(--admin-border-light);
  border-radius: 6px;
  background: var(--admin-bg);
}

.task-config__section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.task-config__section-header h3 {
  margin: 0;
  color: var(--admin-text);
  font-size: 14px;
  font-weight: 600;
}

.task-config__section-header span,
.task-config__sheet span,
.task-config__parameter span {
  color: var(--admin-text-muted);
  font-size: 12px;
}

.task-config__sheet-grid,
.task-config__parameter-list {
  display: grid;
  align-content: start;
  gap: 8px;
}

.task-config__sheet {
  display: grid;
  gap: 4px;
  min-width: 0;
  padding: 11px 12px;
  border: 1px solid var(--admin-border);
  border-radius: 5px;
  background: var(--admin-surface);
}

.task-config__sheet .el-tag {
  justify-self: start;
}

.task-config__sheet strong,
.task-config__sheet span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-config__sheet strong {
  color: var(--admin-text);
  font-size: 13px;
}

.task-config__chips {
  display: flex;
  flex-wrap: wrap;
  align-content: start;
  gap: 8px;
}

.task-config__parameter {
  display: flex;
  align-items: baseline;
  min-width: 0;
  min-height: 36px;
  gap: 4px;
  padding: 7px 10px;
  border: 1px solid var(--admin-border);
  border-radius: 5px;
  background: var(--admin-surface);
}

.task-config__parameter span {
  flex: 0 0 auto;
}

.task-config__parameter code {
  min-width: 0;
  overflow: hidden;
  color: var(--admin-text-regular);
  font: 12px/20px Consolas, "Courier New", monospace;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-config__advanced {
  border-top: 1px solid var(--admin-border-light);
  border-bottom: 1px solid var(--admin-border-light);
}

.task-config__advanced :deep(.el-collapse-item__header),
.task-config__advanced :deep(.el-collapse-item__wrap) {
  border-bottom: 0;
  background: transparent;
}

.task-config__advanced :deep(.el-collapse-item__content) {
  padding-bottom: 12px;
}

.task-config__advanced small {
  margin-left: 8px;
  color: var(--admin-text-muted);
  font-size: 12px;
}

@media (max-width: 900px) {
  .task-config__primary {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 760px) {
  .task-config__settings,
  .task-config__advanced :deep(.el-descriptions) {
    overflow: auto;
  }

  .task-config__settings :deep(.el-descriptions__table),
  .task-config__advanced :deep(.el-descriptions__table) {
    min-width: 620px;
  }
}
</style>
