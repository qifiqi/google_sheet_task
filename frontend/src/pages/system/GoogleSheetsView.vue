<script setup lang="ts">
import { computed, onMounted, reactive, shallowRef } from 'vue'
import { Link, Plus, Refresh } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import SystemPageHeader from '../../components/system/SystemPageHeader.vue'
import { useAuthStore } from '../../stores/auth'
import { useGoogleSheets } from '../../composables/useGoogleSheets'
import { formatDateTime } from '../../utils/format'
import type { GoogleSheetItem } from '../../types/system'

const auth = useAuthStore()
const registry = useGoogleSheets()
const keyword = shallowRef('')
const tableType = shallowRef('')
const activeStatus = shallowRef('')
const usageStatus = shallowRef('')
const dialogVisible = shallowRef(false)
const editing = shallowRef<GoogleSheetItem | null>(null)
const saving = shallowRef(false)
const form = reactive({ name: '', spreadsheet_id: '', table_type: 'c3', remark: '', is_active: true })
const tableTypes = [{ label: 'C3', value: 'c3' }, { label: 'C4', value: 'c4' }, { label: 'C5', value: 'c5' }, { label: 'C7', value: 'c7' }, { label: '单品回测', value: 'backtest_training' }]

const filteredSheets = computed(() => {
  const query = keyword.value.trim().toLowerCase()
  return registry.sheets.value.filter((item) => {
    const matchesType = !tableType.value || item.table_type === tableType.value
    const matchesActive = activeStatus.value === '' || item.is_active === (activeStatus.value === 'active')
    const matchesUsage = usageStatus.value === '' || item.is_in_use === (usageStatus.value === 'in_use')
    const matchesKeyword = !query || `${item.name} ${item.spreadsheet_id} ${item.remark || ''}`.toLowerCase().includes(query)
    return matchesType && matchesActive && matchesUsage && matchesKeyword
  })
})

function canManage() { return auth.hasPermission('google_sheet:manage') }
function typeText(value: string) { return tableTypes.find((item) => item.value === value)?.label || value }
function extractSpreadsheetId(value: string) {
  const input = value.trim()
  return input.match(/\/spreadsheets\/d\/([a-zA-Z0-9-_]+)/)?.[1] || input
}
function googleSheetUrl(spreadsheetId: string) {
  const id = extractSpreadsheetId(spreadsheetId)
  return id ? `https://docs.google.com/spreadsheets/d/${encodeURIComponent(id)}/edit` : ''
}
function openCreate() { editing.value = null; Object.assign(form, { name: '', spreadsheet_id: '', table_type: 'c3', remark: '', is_active: true }); dialogVisible.value = true }
function openEdit(item: GoogleSheetItem) { editing.value = item; Object.assign(form, { name: item.name, spreadsheet_id: item.spreadsheet_id, table_type: item.table_type, remark: item.remark || '', is_active: item.is_active }); dialogVisible.value = true }

async function save() {
  if (!form.name.trim() || !form.spreadsheet_id.trim()) { ElMessage.warning('请填写名称和 Spreadsheet ID'); return }
  saving.value = true
  try {
    await registry.save({ id: editing.value?.id, name: form.name.trim(), spreadsheet_id: extractSpreadsheetId(form.spreadsheet_id), table_type: form.table_type, remark: form.remark.trim(), is_active: form.is_active })
    dialogVisible.value = false
    ElMessage.success(editing.value ? 'Google Sheet 已更新' : 'Google Sheet 已创建')
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '保存 Google Sheet 失败') } finally { saving.value = false }
}

async function remove(item: GoogleSheetItem) {
  try {
    await ElMessageBox.confirm(`删除“${item.name}”后无法恢复，是否继续？`, '删除 Google Sheet', { type: 'error', confirmButtonText: '删除' })
    await registry.remove(item.id)
    ElMessage.success('Google Sheet 已删除')
  } catch (error) { if (error !== 'cancel') ElMessage.error(error instanceof Error ? error.message : '删除 Google Sheet 失败') }
}

onMounted(registry.load)
</script>

<template>
  <section class="google-sheets-page">
    <SystemPageHeader section="系统模块" title="Google Sheet 管理"><el-button :icon="Refresh" @click="registry.load">刷新</el-button><el-button v-if="canManage()" type="primary" :icon="Plus" @click="openCreate">新增 Sheet</el-button></SystemPageHeader>
    <section class="google-sheets-page__panel">
      <div class="google-sheets-page__toolbar"><el-input v-model="keyword" clearable placeholder="搜索名称、ID 或备注" /><el-select v-model="tableType" clearable placeholder="全部类型"><el-option v-for="item in tableTypes" :key="item.value" :label="item.label" :value="item.value" /></el-select><el-select v-model="activeStatus" clearable placeholder="全部启用状态"><el-option label="启用" value="active" /><el-option label="停用" value="inactive" /></el-select><el-select v-model="usageStatus" clearable placeholder="全部占用状态"><el-option label="占用中" value="in_use" /><el-option label="空闲" value="idle" /></el-select><span>共 {{ filteredSheets.length }} 条</span></div>
      <el-alert v-if="registry.errorMessage.value" :title="registry.errorMessage.value" type="error" show-icon :closable="false" />
      <el-table v-loading="registry.loading.value" :data="filteredSheets" empty-text="暂无 Google Sheet">
        <el-table-column prop="id" label="ID" width="72" />
        <el-table-column prop="name" label="名称" min-width="180" show-overflow-tooltip />
        <el-table-column prop="spreadsheet_id" label="Spreadsheet ID" min-width="280"><template #default="{ row }"><code>{{ row.spreadsheet_id }}</code></template></el-table-column>
        <el-table-column label="类型" width="116"><template #default="{ row }"><el-tag type="info" effect="plain">{{ typeText(row.table_type) }}</el-tag></template></el-table-column>
        <el-table-column prop="remark" label="备注" min-width="180" show-overflow-tooltip />
        <el-table-column label="状态" width="150"><template #default="{ row }"><el-tag :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? '启用' : '停用' }}</el-tag><el-tag class="google-sheets-page__tag" :type="row.is_in_use ? 'warning' : 'primary'">{{ row.is_in_use ? '占用中' : '空闲' }}</el-tag></template></el-table-column>
        <el-table-column label="当前任务" width="150" show-overflow-tooltip><template #default="{ row }"><code>{{ row.current_task_id || '-' }}</code></template></el-table-column>
        <el-table-column label="更新时间" width="180"><template #default="{ row }">{{ formatDateTime(row.updated_at) }}</template></el-table-column>
        <el-table-column fixed="right" label="操作" :width="canManage() ? 216 : 104"><template #default="{ row }"><el-button tag="a" link type="primary" :icon="Link" :href="googleSheetUrl(row.spreadsheet_id)" target="_blank" rel="noopener noreferrer">跳转到模型</el-button><template v-if="canManage()"><el-button link type="primary" @click="openEdit(row)">编辑</el-button><el-button link type="danger" :disabled="row.is_in_use" @click="remove(row)">删除</el-button></template></template></el-table-column>
      </el-table>
    </section>
    <el-dialog v-model="dialogVisible" :title="editing ? '编辑 Google Sheet' : '新增 Google Sheet'" width="min(640px, calc(100vw - 32px))" :close-on-click-modal="false">
      <el-form label-position="top" @submit.prevent="save"><div class="google-sheets-page__form-grid"><el-form-item label="名称" required><el-input v-model="form.name" maxlength="255" /></el-form-item><el-form-item label="表类型" required><el-select v-model="form.table_type"><el-option v-for="item in tableTypes" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item></div><el-form-item label="Spreadsheet ID" required><el-input v-model="form.spreadsheet_id" placeholder="请输入 Spreadsheet ID 或完整 Google Sheet URL" /><div class="google-sheets-page__form-help">支持粘贴完整链接，保存时自动提取 Spreadsheet ID</div></el-form-item><el-form-item label="备注"><el-input v-model="form.remark" type="textarea" :rows="3" maxlength="500" show-word-limit /></el-form-item><el-form-item><el-switch v-model="form.is_active" active-text="启用" inactive-text="停用" /></el-form-item></el-form>
      <template #footer><el-button @click="dialogVisible = false">取消</el-button><el-button type="primary" :loading="saving" @click="save">保存</el-button></template>
    </el-dialog>
  </section>
</template>

<style scoped>
.google-sheets-page { display: grid; gap: 16px; }.google-sheets-page__panel { display: grid; gap: 16px; padding: 16px 20px; border: 1px solid var(--admin-border); border-radius: var(--admin-radius); background: var(--admin-surface); }.google-sheets-page__toolbar { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }.google-sheets-page__toolbar :deep(.el-input) { width: 260px; }.google-sheets-page__toolbar :deep(.el-select) { width: 180px; }.google-sheets-page__toolbar span { margin-left: auto; color: var(--admin-text-muted); font-size: 13px; }.google-sheets-page__tag { margin-left: 6px; }.google-sheets-page__form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }.google-sheets-page__form-help { margin-top: 4px; color: var(--admin-text-muted); font-size: 13px; line-height: 20px; }@media (max-width: 640px) { .google-sheets-page__panel { padding: 16px; }.google-sheets-page__toolbar :deep(.el-input), .google-sheets-page__toolbar :deep(.el-select) { width: 100%; }.google-sheets-page__toolbar span { width: 100%; margin-left: 0; }.google-sheets-page__form-grid { grid-template-columns: 1fr; gap: 0; } }
</style>
