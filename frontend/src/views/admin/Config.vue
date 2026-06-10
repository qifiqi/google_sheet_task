<template>
  <div class="admin-config">
    <PageToolbar eyebrow="管理中心" title="系统配置" description="管理系统参数和令牌">
      <template #actions>
        <el-button type="success" :loading="validating" @click="handleValidate">
          <el-icon><CircleCheck /></el-icon> 验证配置
        </el-button>
      </template>
    </PageToolbar>

    <!-- System Configs Table -->
    <el-card shadow="never" class="mb-4">
      <template #header>
        <div class="card-header">
          <span>系统参数</span>
          <el-button text type="primary" @click="loadConfigs">
            <el-icon><Refresh /></el-icon> 刷新
          </el-button>
        </div>
      </template>
      <el-table :data="configs" v-loading="loading" stripe style="width: 100%">
        <el-table-column prop="key" label="参数键" min-width="180" show-overflow-tooltip />
        <el-table-column prop="value" label="参数值" min-width="240" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="config-value">{{ truncateValue(row.value) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="描述" min-width="200" show-overflow-tooltip />
        <el-table-column prop="updated_at" label="更新时间" width="170">
          <template #default="{ row }">
            <span class="cell-time">{{ formatTime(row.updated_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right" align="center">
          <template #default="{ row }">
            <el-button type="primary" size="small" text @click.stop="openEditDialog(row)">编辑</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Token Management -->
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>令牌管理</span>
          <el-button type="primary" size="small" @click="importTokenDialogVisible = true">
            <el-icon><Plus /></el-icon> 导入令牌
          </el-button>
        </div>
      </template>
      <el-table :data="tokens" v-loading="tokensLoading" stripe style="width: 100%">
        <el-table-column prop="email" label="邮箱" min-width="180" show-overflow-tooltip />
        <el-table-column prop="status" label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'danger'" size="small">
              {{ row.is_active ? '有效' : '无效' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="170">
          <template #default="{ row }"><span class="cell-time">{{ formatTime(row.created_at) }}</span></template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right" align="center">
          <template #default="{ row }">
            <el-popconfirm title="确定删除此令牌？" @confirm="handleDeleteToken(row)">
              <template #reference>
                <el-button type="danger" size="small" text @click.stop>删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Edit Config Dialog -->
    <el-dialog v-model="editDialogVisible" title="编辑配置" width="500px" destroy-on-close>
      <el-form :model="editForm" label-width="100px">
        <el-form-item label="参数键">
          <el-input v-model="editForm.key" disabled />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="editForm.description" disabled />
        </el-form-item>
        <el-form-item label="参数值" required>
          <el-input
            v-model="editForm.value"
            type="textarea"
            :rows="5"
            placeholder="请输入参数值"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSaveConfig">保存</el-button>
      </template>
    </el-dialog>

    <!-- Import Token Dialog -->
    <el-dialog v-model="importTokenDialogVisible" title="导入令牌" width="500px" destroy-on-close>
      <el-form :model="importForm" label-width="100px">
        <el-form-item label="令牌文件">
          <el-upload
            ref="uploadRef"
            :auto-upload="false"
            :limit="1"
            accept=".json"
            :on-change="handleTokenFileChange"
          >
            <el-button type="primary">选择 JSON 文件</el-button>
            <template #tip>
              <div class="el-upload__tip">仅支持 .json 格式的令牌文件</div>
            </template>
          </el-upload>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="importForm.remark" placeholder="可选备注" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="importTokenDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="importing" @click="handleImportToken">导入</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { Plus, Refresh, CircleCheck } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { getSystemConfigs, updateSystemConfig, validateConfig } from '@/api/config'
import { getTokens, deleteToken, importToken } from '@/api/googleSheet'
import PageToolbar from '@/components/PageToolbar.vue'

const loading = ref(false)
const configs = ref([])
const tokensLoading = ref(false)
const tokens = ref([])
const validating = ref(false)

// Edit config
const editDialogVisible = ref(false)
const editForm = ref({ key: '', value: '', description: '' })
const saving = ref(false)

// Import token
const importTokenDialogVisible = ref(false)
const importForm = ref({ file_content: '', remark: '' })
const importing = ref(false)
const uploadRef = ref(null)

function formatTime(str) {
  if (!str) return '-'
  return new Date(str).toLocaleString('zh-CN')
}

function truncateValue(val) {
  if (!val) return '-'
  const str = String(val)
  return str.length > 80 ? str.slice(0, 80) + '...' : str
}

async function loadConfigs() {
  loading.value = true
  try {
    const res = await getSystemConfigs()
    const data = res?.data || res || []
    configs.value = Array.isArray(data) ? data : data.items || []
  } catch {
    configs.value = []
  } finally {
    loading.value = false
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

function openEditDialog(row) {
  editForm.value = { key: row.key, value: row.value, description: row.description || '' }
  editDialogVisible.value = true
}

async function handleSaveConfig() {
  saving.value = true
  try {
    await updateSystemConfig(editForm.value.key, { value: editForm.value.value })
    ElMessage.success('配置已更新')
    editDialogVisible.value = false
    loadConfigs()
  } catch {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

async function handleValidate() {
  validating.value = true
  try {
    const res = await validateConfig()
    const data = res?.data || res || {}
    if (data.valid) {
      ElMessage.success('配置验证通过')
    } else {
      ElMessage.warning(`配置验证失败: ${data.message || '未知错误'}`)
    }
  } catch {
    ElMessage.error('验证请求失败')
  } finally {
    validating.value = false
  }
}

function handleTokenFileChange(file) {
  const rawFile = file.raw
  const reader = new FileReader()
  reader.onload = (e) => {
    importForm.value.file_content = e.target.result
  }
  reader.readAsText(rawFile)
}

async function handleImportToken() {
  if (!importForm.value.file_content) {
    ElMessage.warning('请选择令牌文件')
    return
  }
  importing.value = true
  try {
    await importToken({
      token_data: importForm.value.file_content,
      remark: importForm.value.remark,
    })
    ElMessage.success('令牌已导入')
    importTokenDialogVisible.value = false
    importForm.value = { file_content: '', remark: '' }
    loadTokens()
  } catch {
    ElMessage.error('导入失败')
  } finally {
    importing.value = false
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
  loadConfigs()
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

.config-value {
  font-family: 'Fira Code', 'Consolas', monospace;
  font-size: 12px;
}

.cell-time {
  font-size: var(--app-font-sm);
  color: var(--app-text-muted);
  white-space: nowrap;
}
</style>
