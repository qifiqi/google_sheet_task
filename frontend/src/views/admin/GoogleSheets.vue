<template>
  <div class="admin-google-sheets">
    <PageToolbar eyebrow="管理中心" title="Google Sheets 管理" description="管理 Google Sheets 数据和令牌" />

    <!-- Sheets Table -->
    <el-card shadow="never" class="mb-4">
      <template #header>
        <div class="card-header">
          <span>Sheets 列表</span>
          <el-button text type="primary" @click="loadSheets">
            <el-icon><Refresh /></el-icon> 刷新
          </el-button>
        </div>
      </template>
      <el-table :data="sheets" v-loading="sheetsLoading" stripe style="width: 100%">
        <el-table-column prop="sheet_name" label="名称" min-width="180" show-overflow-tooltip />
        <el-table-column prop="sheet_id" label="Sheet ID" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">
            <el-link type="primary" :href="`https://docs.google.com/spreadsheets/d/${row.sheet_id}`" target="_blank">
              {{ row.sheet_id }}
            </el-link>
          </template>
        </el-table-column>
        <el-table-column prop="token_email" label="关联令牌" width="200" show-overflow-tooltip />
        <el-table-column prop="created_at" label="创建时间" width="175" align="center">
          <template #default="{ row }">
            <span class="cell-time">{{ formatTime(row.created_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right" align="center">
          <template #default="{ row }">
            <el-popconfirm title="确定删除此 Sheet？" @confirm="handleDeleteSheet(row)">
              <template #reference>
                <el-button type="danger" size="small" text @click.stop>删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Tokens Section -->
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>令牌管理</span>
          <div>
            <el-button type="primary" size="small" @click="importDialogVisible = true">
              <el-icon><Upload /></el-icon> 导入令牌
            </el-button>
            <el-button text type="primary" @click="loadTokens">
              <el-icon><Refresh /></el-icon>
            </el-button>
          </div>
        </div>
      </template>
      <el-table :data="tokens" v-loading="tokensLoading" stripe style="width: 100%">
        <el-table-column prop="email" label="邮箱" min-width="220" show-overflow-tooltip />
        <el-table-column prop="status" label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'danger'" size="small">
              {{ row.is_active ? '有效' : '无效' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="175" align="center">
          <template #default="{ row }">
            <span class="cell-time">{{ formatTime(row.created_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right" align="center">
          <template #default="{ row }">
            <el-button type="primary" size="small" text @click="openEditTokenDialog(row)">编辑</el-button>
            <el-popconfirm title="确定删除此令牌？" @confirm="handleDeleteToken(row)">
              <template #reference>
                <el-button type="danger" size="small" text @click.stop>删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Import Token Dialog -->
    <el-dialog v-model="importDialogVisible" title="导入令牌" width="500px" destroy-on-close>
      <el-form :model="importForm" label-width="100px">
        <el-form-item label="令牌文件">
          <el-upload
            :auto-upload="false"
            :limit="1"
            accept=".json"
            :on-change="handleFileChange"
          >
            <el-button type="primary">选择 JSON 文件</el-button>
            <template #tip>
              <div class="el-upload__tip">仅支持 .json 格式的 Google 服务账号令牌</div>
            </template>
          </el-upload>
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="importForm.email" placeholder="关联邮箱（可选）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="importDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="importing" @click="handleImport">导入</el-button>
      </template>
    </el-dialog>

    <!-- Edit Token Dialog -->
    <el-dialog v-model="editTokenVisible" title="编辑令牌" width="500px" destroy-on-close>
      <el-form :model="editTokenForm" label-width="100px">
        <el-form-item label="邮箱">
          <el-input v-model="editTokenForm.email" placeholder="关联邮箱" />
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="editTokenForm.is_active" active-text="有效" inactive-text="无效" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editTokenVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingToken" @click="handleSaveToken">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { Refresh, Upload } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { getGoogleSheets, deleteGoogleSheet, getTokens, updateToken, deleteToken, importToken } from '@/api/googleSheet'
import PageToolbar from '@/components/PageToolbar.vue'

const sheetsLoading = ref(false)
const sheets = ref([])
const tokensLoading = ref(false)
const tokens = ref([])

// Import dialog
const importDialogVisible = ref(false)
const importForm = ref({ file_content: '', email: '' })
const importing = ref(false)

// Edit token dialog
const editTokenVisible = ref(false)
const editTokenForm = ref({ id: null, email: '', is_active: true })
const savingToken = ref(false)

function formatTime(str) {
  if (!str) return '-'
  return new Date(str).toLocaleString('zh-CN')
}

async function loadSheets() {
  sheetsLoading.value = true
  try {
    const res = await getGoogleSheets()
    const data = res?.data || res || {}
    sheets.value = data.sheets || data.items || data || []
  } catch {
    sheets.value = []
  } finally {
    sheetsLoading.value = false
  }
}

async function loadTokens() {
  tokensLoading.value = true
  try {
    const res = await getTokens()
    const data = res?.data || res || []
    tokens.value = Array.isArray(data) ? data : data.items || []
  } catch {
    tokens.value = []
  } finally {
    tokensLoading.value = false
  }
}

async function handleDeleteSheet(row) {
  try {
    await deleteGoogleSheet(row.id)
    ElMessage.success('已删除')
    loadSheets()
  } catch {
    ElMessage.error('删除失败')
  }
}

function handleFileChange(file) {
  const reader = new FileReader()
  reader.onload = (e) => {
    importForm.value.file_content = e.target.result
  }
  reader.readAsText(file.raw)
}

async function handleImport() {
  if (!importForm.value.file_content) {
    ElMessage.warning('请选择令牌文件')
    return
  }
  importing.value = true
  try {
    await importToken({
      token_data: importForm.value.file_content,
      email: importForm.value.email,
    })
    ElMessage.success('令牌已导入')
    importDialogVisible.value = false
    importForm.value = { file_content: '', email: '' }
    loadTokens()
  } catch {
    ElMessage.error('导入失败')
  } finally {
    importing.value = false
  }
}

function openEditTokenDialog(row) {
  editTokenForm.value = {
    id: row.id,
    email: row.email || '',
    is_active: row.is_active ?? true,
  }
  editTokenVisible.value = true
}

async function handleSaveToken() {
  savingToken.value = true
  try {
    await updateToken(editTokenForm.value.id, {
      email: editTokenForm.value.email,
      is_active: editTokenForm.value.is_active,
    })
    ElMessage.success('令牌已更新')
    editTokenVisible.value = false
    loadTokens()
  } catch {
    ElMessage.error('保存失败')
  } finally {
    savingToken.value = false
  }
}

async function handleDeleteToken(row) {
  try {
    await deleteToken(row.id)
    ElMessage.success('已删除')
    loadTokens()
  } catch {
    ElMessage.error('删除失败')
  }
}

onMounted(() => {
  loadSheets()
  loadTokens()
})
</script>

<style lang="scss" scoped>
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.mb-4 {
  margin-bottom: 16px;
}

.cell-time {
  font-size: var(--app-font-sm);
  color: var(--app-text-muted);
  white-space: nowrap;
}
</style>
