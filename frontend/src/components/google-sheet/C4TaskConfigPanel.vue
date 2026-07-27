<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ config: Record<string, unknown> }>()
const mapValue = (value: unknown, map: Record<string, string>) => map[String(value || '')] || String(value || '-')
const sheets = computed(() => (Array.isArray(props.config.sheets) ? props.config.sheets : []).filter((value): value is Record<string, unknown> => Boolean(value && typeof value === 'object')))
const productCodes = computed(() => {
  const parameters = props.config.parameters
  if (!Array.isArray(parameters) || !Array.isArray(parameters[0])) return []
  return parameters[0].map(String)
})
const executionItems = computed(() => [
  { label: '统计方式', value: mapValue(props.config.count_mode || 'total', { total: '总数', n_plus_1: 'N+1' }) },
  { label: '市场类型', value: mapValue(props.config.market_type || 'cn', { cn: 'A 股', us: '美股' }) },
  { label: 'K 线复权', value: mapValue(props.config.kline_adjustment || 'forward', { forward: '前复权', back: '后复权', none: '不复权' }) },
  { label: '范围模式', value: Array.isArray(props.config.date_range_mode) ? props.config.date_range_mode.map((value) => mapValue(value, { full: '整年', recent: '近年' })).join('、') || '-' : '-' },
  { label: '数据日期', value: `${props.config.start_date || '-'} 至 ${props.config.end_date || '-'}` },
  { label: '认证方式', value: props.config.token_type === 'json' ? 'Token JSON' : 'Token 文件' },
  { label: 'Token 选择', value: props.config.token_selection_mode === '__random__' ? '随机 Token' : String(props.config.token_name || props.config.token_id || '未选择') },
  { label: '代理', value: props.config.proxy_url ? '已配置' : '未配置' },
])
</script>

<template>
  <div class="c4-task-config">
    <section class="c4-task-config__block"><h3>Google Sheet 配置</h3><el-empty v-if="!sheets.length" description="未配置 Sheet" :image-size="48" /><div v-else class="c4-task-config__sheet-list"><article v-for="(sheet, index) in sheets" :key="`${sheet.spreadsheet_id || sheet.spreadsheetId}-${index}`"><el-tag type="info" effect="plain">Sheet {{ index + 1 }}</el-tag><strong>{{ sheet.title || sheet.spreadsheet_title || '-' }}</strong><span>资源 ID：{{ sheet.spreadsheet_id || sheet.spreadsheetId || '-' }}</span><span>工作表：{{ sheet.sheet_name || sheet.sheetName || '-' }}</span></article></div></section>
    <section class="c4-task-config__block"><h3>产品代码</h3><el-empty v-if="!productCodes.length" description="未配置产品代码" :image-size="48" /><div v-else class="c4-task-config__chips"><el-tag v-for="code in productCodes" :key="code" type="primary" effect="light">{{ code }}</el-tag></div></section>
    <el-descriptions class="c4-task-config__execution" :column="3" border><el-descriptions-item v-for="item in executionItems" :key="item.label" :label="item.label">{{ item.value }}</el-descriptions-item></el-descriptions>
  </div>
</template>

<style scoped>
.c4-task-config { display: grid; gap: 16px; }.c4-task-config__block { display: grid; gap: 10px; }.c4-task-config__block h3 { margin: 0; color: var(--admin-text); font-size: 14px; font-weight: 600; }.c4-task-config__sheet-list { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 8px; }.c4-task-config__sheet-list article { display: grid; gap: 4px; padding: 10px 12px; border: 1px solid var(--admin-border-light); border-radius: 6px; }.c4-task-config__sheet-list strong { color: var(--admin-text); font-size: 13px; }.c4-task-config__sheet-list span { color: var(--admin-text-muted); font-size: 12px; }.c4-task-config__chips { display: flex; flex-wrap: wrap; gap: 8px; }.c4-task-config__execution { margin-top: 4px; }
</style>
