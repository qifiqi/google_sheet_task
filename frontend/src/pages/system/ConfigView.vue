<script setup lang="ts">
import { h, onMounted, reactive, shallowRef } from 'vue'
import { Plus, Refresh, WarningFilled } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import SystemPageHeader from '../../components/system/SystemPageHeader.vue'
import { useAuth } from '../../composables/useAuth'
import { useSystemConfig } from '../../composables/useSystemConfig'
import { formatDateTime } from '../../utils/format'
import type { GoogleSheetToken, SystemConfigItem } from '../../types/system'

const auth = useAuth()
const systemConfig = useSystemConfig()
const configDialogVisible = shallowRef(false)
const tokenDialogVisible = shallowRef(false)
const editingConfig = shallowRef<SystemConfigItem | null>(null)
const editingToken = shallowRef<GoogleSheetToken | null>(null)
const saving = shallowRef(false)
const configForm = reactive({ key: '', value: '', description: '' })
const tokenForm = reactive({ name: '', task_type: 'google_sheet', max_usage_count: 0, is_active: true, token_context: '' })

function canManageConfig() { return auth.hasPermission('config:manage') }
function canViewTokens() { return auth.hasPermission('google_sheet:view') }
function canManageTokens() { return auth.hasPermission('google_sheet:manage') }
function formatLimit(value: number) { return value > 0 ? String(value) : '不限' }

function openConfigEditor(item: SystemConfigItem) {
  editingConfig.value = item
  configForm.key = item.key
  configForm.value = item.value || ''
  configForm.description = item.description || ''
  configDialogVisible.value = true
}

function openTokenImport() {
  editingToken.value = null
  Object.assign(tokenForm, { name: '', task_type: 'google_sheet', max_usage_count: 0, is_active: true, token_context: '' })
  tokenDialogVisible.value = true
}

async function openTokenEditor(token: GoogleSheetToken) {
  try {
    const detail = await systemConfig.getToken(token.id)
    editingToken.value = detail
    Object.assign(tokenForm, { name: detail.name, task_type: detail.task_type, max_usage_count: detail.max_usage_count, is_active: detail.is_active, token_context: detail.token_context || '' })
    tokenDialogVisible.value = true
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '加载 Token 详情失败') }
}

async function saveConfig() {
  if (!editingConfig.value) return
  saving.value = true
  try {
    await systemConfig.updateConfig({ key: configForm.key, value: configForm.value, description: configForm.description })
    configDialogVisible.value = false
    ElMessage.success('系统配置已更新')
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '保存系统配置失败') } finally { saving.value = false }
}

async function saveToken() {
  if (!tokenForm.token_context.trim()) { ElMessage.warning('请输入 Token JSON 内容'); return }
  saving.value = true
  try {
    if (editingToken.value) {
      await systemConfig.updateToken({ ...editingToken.value, ...tokenForm })
      ElMessage.success('Token 已更新')
    } else {
      await systemConfig.importToken({ ...tokenForm, name: tokenForm.name.trim(), token_context: tokenForm.token_context.trim() })
      ElMessage.success('Token 已导入')
    }
    tokenDialogVisible.value = false
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '保存 Token 失败') } finally { saving.value = false }
}

async function removeToken(token: GoogleSheetToken) {
  try {
    await ElMessageBox.confirm(`删除 Token “${token.name}”后无法恢复，是否继续？`, '删除 Token', { type: 'error', confirmButtonText: '删除' })
    await systemConfig.removeToken(token.id)
    ElMessage.success('Token 已删除')
  } catch (error) { if (error !== 'cancel') ElMessage.error(error instanceof Error ? error.message : '删除 Token 失败') }
}

async function validateConfig() {
  try {
    const payload = await systemConfig.validate()
    await ElMessageBox.alert(h('pre', JSON.stringify(payload.validation, null, 2)), '配置校验结果', { confirmButtonText: '关闭' })
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '配置校验失败') }
}

async function refresh() {
  await systemConfig.loadConfigs()
  if (canViewTokens()) await systemConfig.loadTokens()
}

onMounted(refresh)
</script>

<template>
  <section class="system-config-page">
    <SystemPageHeader section="系统模块" title="系统配置">
      <el-button :icon="Refresh" aria-label="刷新系统配置" @click="refresh">刷新</el-button>
      <el-button v-if="canManageConfig()" :icon="WarningFilled" @click="validateConfig">校验配置</el-button>
    </SystemPageHeader>

    <el-alert v-if="systemConfig.errorMessage.value" :title="systemConfig.errorMessage.value" type="error" show-icon :closable="false" />

    <section class="system-config-page__panel">
      <div class="system-config-page__panel-header"><h2>配置列表</h2><span>{{ systemConfig.configs.value.length }} 项</span></div>
      <el-table v-loading="systemConfig.loading.value" :data="systemConfig.configs.value" empty-text="暂无系统配置">
        <el-table-column prop="key" label="Key" min-width="220"><template #default="{ row }"><code>{{ row.key }}</code></template></el-table-column>
        <el-table-column prop="value" label="Value" min-width="260" show-overflow-tooltip />
        <el-table-column prop="description" label="说明" min-width="240" show-overflow-tooltip />
        <el-table-column v-if="canManageConfig()" fixed="right" label="操作" width="84"><template #default="{ row }"><el-button link type="primary" @click="openConfigEditor(row)">编辑</el-button></template></el-table-column>
      </el-table>
    </section>

    <template v-if="canViewTokens()">
      <section class="system-config-page__metrics">
        <article><span>当前占用</span><strong>{{ systemConfig.tokenSummary.value.current_total_in_use }}</strong></article>
        <article><span>累计使用</span><strong>{{ systemConfig.tokenSummary.value.current_total_usage }}</strong></article>
        <article><span>占用上限</span><strong>{{ formatLimit(systemConfig.tokenSummary.value.global_max_usage) }}</strong></article>
        <article><span>可用 Token</span><strong>{{ systemConfig.tokenSummary.value.available_token_count }}</strong></article>
      </section>
      <section class="system-config-page__panel">
        <div class="system-config-page__panel-header"><div><h2>Google Sheet Token 池</h2><span>资源占用与有效性</span></div><el-button v-if="canManageTokens()" type="primary" :icon="Plus" @click="openTokenImport">导入 Token</el-button></div>
        <el-table v-loading="systemConfig.loading.value" :data="systemConfig.tokens.value" empty-text="暂无 Token">
          <el-table-column prop="id" label="ID" width="72" />
          <el-table-column prop="name" label="名称" min-width="160" show-overflow-tooltip />
          <el-table-column prop="task_type" label="任务类型" width="140"><template #default="{ row }"><code>{{ row.task_type }}</code></template></el-table-column>
          <el-table-column prop="current_in_use_count" label="占用" width="88" align="right" />
          <el-table-column prop="task_usage_count" label="累计使用" width="104" align="right" />
          <el-table-column label="上限" width="88" align="right"><template #default="{ row }">{{ formatLimit(row.max_usage_count) }}</template></el-table-column>
          <el-table-column label="状态" width="148"><template #default="{ row }"><el-tag :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? '启用' : '停用' }}</el-tag><el-tag class="system-config-page__tag" :type="row.is_available ? 'primary' : 'warning'">{{ row.is_available ? '可用' : '已达上限' }}</el-tag></template></el-table-column>
          <el-table-column label="最后使用" width="180"><template #default="{ row }">{{ formatDateTime(row.last_used_at) }}</template></el-table-column>
          <el-table-column v-if="canManageTokens()" fixed="right" label="操作" width="128"><template #default="{ row }"><el-button link type="primary" @click="openTokenEditor(row)">编辑</el-button><el-button link type="danger" @click="removeToken(row)">删除</el-button></template></el-table-column>
        </el-table>
      </section>
    </template>

    <el-dialog v-model="configDialogVisible" title="编辑系统配置" width="min(620px, calc(100vw - 32px))" :close-on-click-modal="false">
      <el-form label-position="top"><el-form-item label="Key"><el-input v-model="configForm.key" disabled /></el-form-item><el-form-item label="Value"><el-input v-model="configForm.value" type="textarea" :rows="5" /></el-form-item><el-form-item label="说明"><el-input v-model="configForm.description" type="textarea" :rows="3" /></el-form-item></el-form>
      <template #footer><el-button @click="configDialogVisible = false">取消</el-button><el-button type="primary" :loading="saving" @click="saveConfig">保存</el-button></template>
    </el-dialog>

    <el-dialog v-model="tokenDialogVisible" :title="editingToken ? '编辑 Token' : '导入 Token'" width="min(720px, calc(100vw - 32px))" :close-on-click-modal="false">
      <el-form label-position="top"><div class="system-config-page__dialog-grid"><el-form-item label="名称"><el-input v-model="tokenForm.name" placeholder="Token 展示名称" /></el-form-item><el-form-item label="任务类型"><el-select v-model="tokenForm.task_type"><el-option label="Google Sheet" value="google_sheet" /><el-option label="Backtest Training" value="backtest_training" /></el-select></el-form-item><el-form-item label="最大同时占用"><el-input-number v-model="tokenForm.max_usage_count" :min="0" /></el-form-item></div><el-form-item label="启用状态"><el-switch v-model="tokenForm.is_active" active-text="启用" inactive-text="停用" /></el-form-item><el-form-item label="Token JSON" required><el-input v-model="tokenForm.token_context" type="textarea" :rows="10" spellcheck="false" placeholder="粘贴 OAuth Token JSON" /></el-form-item></el-form>
      <template #footer><el-button @click="tokenDialogVisible = false">取消</el-button><el-button type="primary" :loading="saving" @click="saveToken">保存</el-button></template>
    </el-dialog>
  </section>
</template>

<style scoped>
.system-config-page { display: grid; gap: 16px; }.system-config-page__panel { display: grid; gap: 16px; padding: 16px 20px; border: 1px solid var(--admin-border); border-radius: var(--admin-radius); background: var(--admin-surface); }.system-config-page__panel-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }.system-config-page__panel-header div { display: grid; gap: 2px; }.system-config-page__panel-header h2 { margin: 0; color: var(--admin-text); font-size: 16px; font-weight: 600; }.system-config-page__panel-header span { color: var(--admin-text-muted); font-size: 13px; }.system-config-page__metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; }.system-config-page__metrics article { display: grid; gap: 6px; min-height: 120px; padding: 20px; border: 1px solid var(--admin-border); border-radius: var(--admin-radius); background: var(--admin-surface); }.system-config-page__metrics span { color: var(--admin-text-muted); font-size: 13px; }.system-config-page__metrics strong { color: var(--admin-text); font-size: 28px; font-weight: 600; }.system-config-page__tag { margin-left: 6px; }.system-config-page__dialog-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; }@media (max-width: 1024px) { .system-config-page__metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }.system-config-page__dialog-grid { grid-template-columns: 1fr; gap: 0; } }@media (max-width: 640px) { .system-config-page__metrics { grid-template-columns: 1fr; }.system-config-page__panel { padding: 16px; } }
</style>
