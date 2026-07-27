<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ config: Record<string, unknown> }>()

const sheets = computed(() => [{
  id: String(props.config.spreadsheet_id || props.config.spreadsheetId || ''),
  title: String(props.config.title || props.config.spreadsheet_title || '-'),
  worksheet: String(props.config.sheet_name || props.config.sheetName || '-'),
}].filter((sheet) => sheet.id || sheet.title !== '-'))
const parameterGroups = computed(() => Array.isArray(props.config.parameters) ? props.config.parameters : [])
const stockLabel = computed(() => [props.config.stock_code, props.config.stock_name].filter(Boolean).map(String).join(' / ') || '-')
const executionItems = computed(() => [
  { label: '标的', value: stockLabel.value },
  { label: '结束日期', value: String(props.config.end_date || '-') },
  { label: '回溯年数', value: props.config.year_n ? `${props.config.year_n} 年` : '-' },
  { label: '认证方式', value: props.config.token_type === 'json' ? 'Token JSON' : 'Token 文件' },
  { label: 'Token 选择', value: props.config.token_selection_mode === '__random__' ? '随机 Token' : String(props.config.token_name || props.config.token_id || '未选择') },
  { label: '代理', value: props.config.proxy_url ? '已配置' : '未配置' },
].filter((item) => item.value !== '-'))
</script>

<template>
  <div class="c3-task-config">
    <section class="c3-task-config__block">
      <h3>Google Sheet 配置</h3>
      <el-empty v-if="!sheets.length" description="未配置 Sheet" :image-size="48" />
      <div v-else class="c3-task-config__sheet-list">
        <article v-for="sheet in sheets" :key="sheet.id"><strong>{{ sheet.title }}</strong><span>资源 ID：{{ sheet.id }}</span><span>工作表：{{ sheet.worksheet }}</span></article>
      </div>
    </section>
    <section class="c3-task-config__block">
      <h3>参数配置</h3>
      <el-empty v-if="!parameterGroups.length" description="无参数配置" :image-size="48" />
      <div v-else class="c3-task-config__parameters"><div v-for="(group, index) in parameterGroups" :key="index"><el-tag type="primary" effect="light">参数 {{ index + 1 }}</el-tag><code>{{ JSON.stringify(group) }}</code></div></div>
    </section>
    <el-descriptions class="c3-task-config__execution" :column="3" border>
      <el-descriptions-item v-for="item in executionItems" :key="item.label" :label="item.label">{{ item.value }}</el-descriptions-item>
    </el-descriptions>
  </div>
</template>

<style scoped>
.c3-task-config { display: grid; gap: 16px; }.c3-task-config__block { display: grid; gap: 10px; min-width: 0; }.c3-task-config__block h3 { margin: 0; color: var(--admin-text); font-size: 14px; font-weight: 600; }.c3-task-config__sheet-list, .c3-task-config__parameters { display: grid; gap: 8px; }.c3-task-config__sheet-list article { display: grid; gap: 3px; padding: 10px 12px; border: 1px solid var(--admin-border-light); border-radius: 6px; }.c3-task-config__sheet-list strong { color: var(--admin-text); font-size: 13px; }.c3-task-config__sheet-list span { color: var(--admin-text-muted); font-size: 12px; }.c3-task-config__parameters > div { display: flex; align-items: start; gap: 8px; padding: 8px 0; border-bottom: 1px solid var(--admin-border-light); }.c3-task-config__parameters code { min-width: 0; overflow-wrap: anywhere; color: var(--admin-text-regular); font-size: 12px; white-space: pre-wrap; }.c3-task-config__execution { margin-top: 4px; }
</style>
