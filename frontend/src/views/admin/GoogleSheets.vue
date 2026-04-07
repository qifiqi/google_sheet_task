<template>
  <div class="app-page google-sheets-page">
    <div class="page-toolbar">
      <div class="page-toolbar__meta">
        <div class="page-toolbar__eyebrow">管理后台</div>
        <h2 class="page-title">Google Sheet 管理</h2>
      </div>
      <div class="page-toolbar__actions">
        <el-button type="primary" @click="openCreate">新增表格</el-button>
      </div>
    </div>

    <el-card shadow="never" class="section-card">
      <el-row :gutter="12" align="bottom">
        <el-col :xs="24" :sm="8" :md="5">
          <el-input v-model="filters.keyword" placeholder="名称 / Spreadsheet ID" clearable @input="applyFilter" />
        </el-col>
        <el-col :xs="12" :sm="4" :md="3">
          <el-select v-model="filters.active" placeholder="状态" clearable class="full-width" @change="applyFilter">
            <el-option value="1" label="启用" />
            <el-option value="0" label="停用" />
          </el-select>
        </el-col>
        <el-col :xs="12" :sm="4" :md="3">
          <el-select v-model="filters.tableType" placeholder="表格类型" clearable class="full-width" @change="applyFilter">
            <el-option v-for="opt in tableTypeOptions" :key="opt.value" :value="opt.value" :label="opt.label" />
          </el-select>
        </el-col>
        <el-col :xs="12" :sm="4" :md="3">
          <el-select v-model="filters.usage" placeholder="占用情况" clearable class="full-width" @change="applyFilter">
            <el-option value="1" label="使用中" />
            <el-option value="0" label="空闲" />
          </el-select>
        </el-col>
        <el-col :xs="12" :sm="4" :md="2">
          <el-button @click="loadSheets">刷新</el-button>
        </el-col>
      </el-row>
    </el-card>

    <el-table :data="filteredSheets" v-loading="loading" stripe>
      <el-table-column prop="name" label="名称" min-width="120" />
      <el-table-column label="Spreadsheet ID" min-width="200">
        <template #default="{ row }">
          <code class="mono-inline">{{ row.spreadsheet_id }}</code>
        </template>
      </el-table-column>
      <el-table-column label="表格类型" width="100">
        <template #default="{ row }">
          <el-tag size="small">{{ (row.table_type || '').toUpperCase() }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="remark" label="备注" min-width="120" show-overflow-tooltip />
      <el-table-column label="启用" width="80">
        <template #default="{ row }">
          <el-tag :type="row.is_active ? 'success' : 'info'" size="small">{{ row.is_active ? '启用' : '停用' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="占用" width="90">
        <template #default="{ row }">
          <el-tag :type="row.is_in_use ? 'warning' : ''" size="small">{{ row.is_in_use ? '使用中' : '空闲' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="当前任务" min-width="160" show-overflow-tooltip>
        <template #default="{ row }">
          <code class="mono-inline">{{ row.current_task_id || '-' }}</code>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="120">
        <template #default="{ row }">
          <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button link type="danger" :disabled="row.is_in_use" @click="handleDelete(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑表格' : '新增表格'" width="480px" :fullscreen="isMobile">
      <el-form :model="form" label-width="110px">
        <el-form-item label="名称">
          <el-input v-model="form.name" placeholder="例如：主表 A" />
        </el-form-item>
        <el-form-item label="Spreadsheet ID">
          <el-input v-model="form.spreadsheet_id" placeholder="Google Sheet ID 或完整 URL" />
          <div class="helper-text">支持直接粘贴 Google Sheet URL，系统会自动提取 ID。</div>
        </el-form-item>
        <el-form-item label="表格类型">
          <el-select v-model="form.table_type" class="full-width">
            <el-option v-for="opt in tableTypeOptions" :key="opt.value" :value="opt.value" :label="opt.label" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.is_active" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getGoogleSheets, createGoogleSheet, updateGoogleSheet, deleteGoogleSheet } from '@/api/googleSheet'
import { getEnums } from '@/api/meta'
import { useResponsive } from '@/composables/useResponsive'

const { isMobile } = useResponsive()
const sheets = ref([])
const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const editingId = ref(null)
const tableTypeOptions = ref([])
const filters = reactive({ keyword: '', active: '', tableType: '', usage: '' })
const form = reactive({ name: '', spreadsheet_id: '', table_type: '', remark: '', is_active: true })

const filteredSheets = computed(() => {
  return sheets.value.filter(item => {
    const kw = filters.keyword.toLowerCase()
    const matchKw = !kw || (item.name || '').toLowerCase().includes(kw) || (item.spreadsheet_id || '').toLowerCase().includes(kw)
    const matchActive = filters.active === '' || String(Number(!!item.is_active)) === filters.active
    const matchUsage = filters.usage === '' || String(Number(!!item.is_in_use)) === filters.usage
    const matchType = !filters.tableType || String(item.table_type || '') === filters.tableType
    return matchKw && matchActive && matchUsage && matchType
  })
})

function applyFilter() {}

function extractSpreadsheetId(input) {
  if (!input) return ''
  const match = input.match(/\/spreadsheets\/d\/([a-zA-Z0-9-_]+)/)
  return match ? match[1] : input.trim()
}

async function loadSheets() {
  loading.value = true
  try {
    const res = await getGoogleSheets({ include_inactive: 1 })
    sheets.value = res.items || []
    if (!tableTypeOptions.value.length) {
      try {
        const metaRes = await getEnums()
        tableTypeOptions.value = metaRes.data?.google_sheet_table_type_options || []
      } catch {
        tableTypeOptions.value = []
      }
    }
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingId.value = null
  form.name = ''
  form.spreadsheet_id = ''
  form.table_type = tableTypeOptions.value[0]?.value || ''
  form.remark = ''
  form.is_active = true
  dialogVisible.value = true
}

function openEdit(row) {
  editingId.value = row.id
  form.name = row.name || ''
  form.spreadsheet_id = row.spreadsheet_id || ''
  form.table_type = row.table_type || ''
  form.remark = row.remark || ''
  form.is_active = !!row.is_active
  dialogVisible.value = true
}

async function handleSave() {
  const payload = {
    name: form.name,
    spreadsheet_id: extractSpreadsheetId(form.spreadsheet_id),
    table_type: form.table_type,
    remark: form.remark,
    is_active: form.is_active
  }

  if (!payload.spreadsheet_id) {
    ElMessage.warning('请输入 Spreadsheet ID')
    return
  }

  saving.value = true
  try {
    if (editingId.value) {
      await updateGoogleSheet(editingId.value, payload)
    } else {
      await createGoogleSheet(payload)
    }
    ElMessage.success('保存成功')
    dialogVisible.value = false
    loadSheets()
  } catch {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

async function handleDelete(id) {
  await ElMessageBox.confirm('确定删除这条 Google Sheet 配置吗？', '确认删除', { type: 'warning' })
  await deleteGoogleSheet(id)
  ElMessage.success('删除成功')
  loadSheets()
}

onMounted(loadSheets)
</script>

<style scoped>
.google-sheets-page :deep(.el-dialog__body) {
  padding-top: 12px;
}
</style>
