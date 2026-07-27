<script setup lang="ts">
import { shallowRef, watch } from 'vue'
import { Plus, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { requestJson } from '../../api/http'
import type { GoogleSheetExecutionSettings, GoogleSheetTokenOption } from '../../types/google-sheet'

const model = defineModel<GoogleSheetExecutionSettings>({ required: true })
const props = withDefaults(defineProps<{ showHeader?: boolean }>(), { showHeader: true })
const tokens = shallowRef<GoogleSheetTokenOption[]>([])
const randomToken = shallowRef('__random__')
const loading = shallowRef(false)
const importPath = shallowRef('')

function update(patch: Partial<GoogleSheetExecutionSettings>) { model.value = { ...model.value, ...patch } }
async function loadTokens() {
  loading.value = true
  try {
    const payload = await requestJson<{ status: string; tokens: GoogleSheetTokenOption[]; random_value: string }>('/api/google-sheet-tokens')
    tokens.value = payload.tokens || []; randomToken.value = payload.random_value || '__random__'
    if (model.value.tokenType === 'file' && !model.value.tokenId) update({ tokenId: randomToken.value })
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '加载 Token 失败') } finally { loading.value = false }
}
async function importToken() {
  if (!importPath.value.trim()) return
  try {
    const payload = await requestJson<{ status: string; token?: GoogleSheetTokenOption; message?: string }>('/api/google-sheet-tokens/import', { method: 'POST', body: JSON.stringify({ token_file: importPath.value.trim() }) })
    importPath.value = ''; await loadTokens(); if (payload.token) update({ tokenId: String(payload.token.id), tokenFile: '' }); ElMessage.success(payload.message || 'Token 已导入')
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '导入 Token 失败') }
}
watch(() => model.value.tokenType, (value) => { if (value === 'file' && !model.value.tokenId) update({ tokenId: randomToken.value }) })
loadTokens()
</script>

<template>
  <section class="execution-settings">
    <header v-if="props.showHeader"><h2>执行配置</h2><p>默认使用资源池中的随机 Token；只有需要固定凭据时才选择指定 Token。</p></header>
    <div class="execution-settings__grid">
      <el-form-item label="认证方式"><el-segmented :model-value="model.tokenType" :options="[{ label: 'Token 资源池', value: 'file' }, { label: 'Token JSON', value: 'json' }]" @update:model-value="(value) => update({ tokenType: value as 'file' | 'json' })" /></el-form-item>
      <el-form-item v-if="model.tokenType === 'file'" label="Token"><div class="execution-settings__token"><el-select :model-value="model.tokenId" :loading="loading" @update:model-value="(value) => update({ tokenId: value })"><el-option :label="'随机 Token（按最低使用数均衡分配）'" :value="randomToken" /><el-option v-for="token in tokens" :key="token.id" :label="`${token.name} | 占用 ${token.current_in_use_count} | 累计 ${token.task_usage_count}`" :value="String(token.id)" :disabled="!token.is_available" /></el-select><el-button :icon="Refresh" aria-label="刷新 Token" :loading="loading" @click="loadTokens" /></div></el-form-item>
      <el-form-item v-else label="Token JSON"><el-input :model-value="model.tokenJson" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }" placeholder='{"installed": {...}}' @update:model-value="(value) => update({ tokenJson: value })" /></el-form-item>
      <el-form-item label="代理 URL"><el-input :model-value="model.proxyUrl" clearable placeholder="可选" @update:model-value="(value) => update({ proxyUrl: value })" /></el-form-item>
    </div>
    <div v-if="model.tokenType === 'file'" class="execution-settings__import"><el-input v-model="importPath" placeholder="输入 Token 文件路径后导入" /><el-button :icon="Plus" @click="importToken">导入</el-button></div>
  </section>
</template>

<style scoped>
.execution-settings { display: grid; gap: 16px; }.execution-settings h2 { margin: 0; color: var(--admin-text); font-size: 16px; font-weight: 600; }.execution-settings p { margin: 4px 0 0; color: var(--admin-text-muted); font-size: 13px; }.execution-settings__grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px 16px; }.execution-settings__grid :deep(.el-form-item) { margin-bottom: 0; }.execution-settings__token { display: grid; grid-template-columns: minmax(0, 1fr) 32px; width: 100%; gap: 8px; }.execution-settings__token :deep(.el-select) { min-width: 0; width: 100%; }.execution-settings__import { display: flex; max-width: 480px; gap: 8px; }.execution-settings__import :deep(.el-input) { width: 100%; }@media (max-width: 768px) { .execution-settings__grid { grid-template-columns: 1fr; }.execution-settings__import { max-width: none; } }
</style>
