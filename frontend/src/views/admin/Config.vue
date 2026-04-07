<template>
  <div class="">
    <div class="page-toolbar">
      <h2 style="margin: 0">系统配置</h2>
      <div class="page-toolbar__actions">
        <el-button :size="componentSize" @click="loadAll">刷新</el-button>
        <el-button type="info" :size="componentSize" @click="handleValidate">校验配置</el-button>
      </div>
    </div>

    <el-row :gutter="12" style="margin-bottom: 16px">
      <el-col
        v-for="card in tokenSummaryCards"
        :key="card.key"
        :xs="12"
        :sm="6"
        style="margin-bottom: 12px"
      >
        <el-card shadow="never">
          <div class="inline-muted">{{ card.label }}</div>
          <div class="config-metric">{{ tokenSummary[card.key] ?? 0 }}</div>
        </el-card>
      </el-col>
    </el-row>

    <div class="page-stack">
      <el-card shadow="never">
        <template #header>配置列表</template>
        <el-table :data="configs" v-loading="loadingConfig" stripe>
          <el-table-column prop="key" label="Key" width="220">
            <template #default="{ row }">
              <code>{{ row.key }}</code>
            </template>
          </el-table-column>
          <el-table-column prop="value" label="Value" min-width="220" show-overflow-tooltip />
          <el-table-column prop="description" label="说明" min-width="220" show-overflow-tooltip />
          <el-table-column label="操作" width="90">
            <template #default="{ row }">
              <el-button link type="primary" @click="openEditConfig(row)">编辑</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-card shadow="never">
        <template #header>
          <div class="card-header-row">
            <span>Google Sheet Token 管理</span>
            <el-button :size="componentSize" @click="loadTokens">刷新 Token</el-button>
          </div>
        </template>

        <el-form :model="importForm" :label-width="formLabelWidth" style="margin-bottom: 16px">
          <el-row :gutter="12">
            <el-col :xs="24" :sm="8" :md="6">
              <el-form-item label="名称">
                <el-input v-model="importForm.name" placeholder="可选，自定义名称" />
              </el-form-item>
            </el-col>
            <el-col :xs="12" :sm="6" :md="4">
              <el-form-item label="占用上限">
                <el-input-number
                  v-model="importForm.max_usage_count"
                  :min="0"
                  placeholder="0 = 不限制"
                  style="width: 100%"
                />
              </el-form-item>
            </el-col>
            <el-col :xs="12" :sm="6" :md="4">
              <el-form-item label="Task Type">
                <el-select v-model="importForm.task_type" style="width: 100%">
                  <el-option value="google_sheet" label="google_sheet" />
                  <el-option value="backtest_training" label="backtest_training" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :xs="24" :sm="24" :md="10">
              <el-form-item label="Token JSON">
                <el-input
                  v-model="importForm.token_context"
                  type="textarea"
                  :rows="4"
                  placeholder="粘贴 token JSON 文本"
                />
              </el-form-item>
            </el-col>
          </el-row>
          <div class="config-actions">
            <el-button type="primary" :size="componentSize" :loading="importing" @click="handleImportToken">
              新增 Token
            </el-button>
          </div>
        </el-form>

        <el-table :data="tokens" v-loading="loadingTokens" stripe>
          <el-table-column prop="id" label="ID" width="60" />
          <el-table-column prop="name" label="名称" min-width="120" />
          <el-table-column prop="task_type" label="Task Type" width="160">
            <template #default="{ row }">
              <code>{{ row.task_type || 'google_sheet' }}</code>
            </template>
          </el-table-column>
          <el-table-column prop="token_context_size" label="JSON 大小" width="90" />
          <el-table-column prop="current_in_use_count" label="当前占用" width="90" />
          <el-table-column prop="task_usage_count" label="累计使用" width="90" />
          <el-table-column label="占用上限" width="90">
            <template #default="{ row }">
              {{ row.max_usage_count > 0 ? row.max_usage_count : '无限' }}
            </template>
          </el-table-column>
          <el-table-column label="状态" width="140">
            <template #default="{ row }">
              <el-tag :type="row.is_active ? 'success' : 'info'" size="small" style="margin-right: 4px">
                {{ row.is_active ? '启用' : '停用' }}
              </el-tag>
              <el-tag :type="row.is_available ? 'primary' : 'warning'" size="small">
                {{ row.is_available ? '可用' : '已达上限' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="last_used_at" label="最后使用" width="170" show-overflow-tooltip />
          <el-table-column label="操作" width="90">
            <template #default="{ row }">
              <el-button link type="primary" @click="openEditToken(row.id)">编辑</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </div>

    <el-dialog v-model="configDialogVisible" title="编辑配置" :width="dialogWidth">
      <el-form :model="configForm" :label-width="formLabelWidth">
        <el-form-item label="Key">
          <el-input v-model="configForm.key" disabled />
        </el-form-item>
        <el-form-item label="Value">
          <el-input v-model="configForm.value" type="textarea" :rows="5" />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="configForm.description" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button :size="componentSize" @click="configDialogVisible = false">取消</el-button>
        <el-button type="primary" :size="componentSize" :loading="savingConfig" @click="handleSaveConfig">
          保存
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="tokenDialogVisible" title="编辑 Token" :width="dialogWidth">
      <el-form :model="tokenForm" :label-width="formLabelWidth">
        <el-row :gutter="12">
          <el-col :xs="24" :sm="12">
            <el-form-item label="名称">
              <el-input v-model="tokenForm.name" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="Task Type">
              <el-select v-model="tokenForm.task_type" style="width: 100%">
                <el-option value="google_sheet" label="google_sheet" />
                <el-option value="backtest_training" label="backtest_training" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="占用上限">
              <el-input-number v-model="tokenForm.max_usage_count" :min="0" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="状态">
              <el-select v-model="tokenForm.is_active" style="width: 100%">
                <el-option :value="true" label="启用" />
                <el-option :value="false" label="停用" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="Token 内容">
              <el-input v-model="tokenForm.token_context" type="textarea" :rows="10" spellcheck="false" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button type="danger" :size="componentSize" @click="handleDeleteToken">删除 Token</el-button>
          <div class="dialog-footer__actions">
            <el-button :size="componentSize" @click="tokenDialogVisible = false">取消</el-button>
            <el-button type="primary" :size="componentSize" :loading="savingToken" @click="handleSaveToken">
              保存
            </el-button>
          </div>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getSystemConfigs, updateSystemConfig, validateConfig } from '@/api/config'
import { deleteToken, getToken, getTokens, importToken, updateToken } from '@/api/googleSheet'
import { useResponsive } from '@/composables/useResponsive'

const { componentSize, dialogWidth, formLabelWidth } = useResponsive()

const configs = ref([])
const tokens = ref([])
const tokenSummary = ref({})
const loadingConfig = ref(false)
const loadingTokens = ref(false)
const importing = ref(false)
const savingConfig = ref(false)
const savingToken = ref(false)
const configDialogVisible = ref(false)
const tokenDialogVisible = ref(false)

const tokenSummaryCards = [
  { key: 'current_total_in_use', label: '当前占用总数' },
  { key: 'current_total_usage', label: '累计使用总数' },
  { key: 'global_max_usage', label: '全局占用上限' },
  { key: 'available_token_count', label: '可用 Token 数' },
]

const configForm = reactive({
  key: '',
  value: '',
  description: '',
})

const tokenForm = reactive({
  id: null,
  name: '',
  task_type: 'google_sheet',
  max_usage_count: 0,
  is_active: true,
  token_context: '',
})

const importForm = reactive({
  name: '',
  max_usage_count: 0,
  task_type: 'google_sheet',
  token_context: '',
})

async function loadAll() {
  await Promise.all([loadConfigs(), loadTokens()])
}

async function loadConfigs() {
  loadingConfig.value = true
  try {
    const res = await getSystemConfigs()
    configs.value = res.configs || []
  } finally {
    loadingConfig.value = false
  }
}

async function loadTokens() {
  loadingTokens.value = true
  try {
    const res = await getTokens()
    tokens.value = res.tokens || []
    tokenSummary.value = res.summary || {}
  } finally {
    loadingTokens.value = false
  }
}

function openEditConfig(row) {
  configForm.key = row.key
  configForm.value = row.value
  configForm.description = row.description || ''
  configDialogVisible.value = true
}

async function handleSaveConfig() {
  savingConfig.value = true
  try {
    await updateSystemConfig(configForm.key, {
      value: configForm.value,
      description: configForm.description,
    })
    ElMessage.success('配置更新成功')
    configDialogVisible.value = false
    await loadConfigs()
  } catch {
    ElMessage.error('配置更新失败')
  } finally {
    savingConfig.value = false
  }
}

async function handleValidate() {
  try {
    const res = await validateConfig()
    const validation = res.validation || {}
    await ElMessageBox.alert(
      `数据库配置数量: ${validation.db_size}\n缓存配置数量: ${validation.cache_size}\nGoogle Sheet 配置: ${JSON.stringify(validation.google_sheet_config, null, 2)}`,
      '配置校验结果',
      { confirmButtonText: '确定' },
    )
  } catch {
    ElMessage.error('配置校验失败')
  }
}

async function handleImportToken() {
  if (!importForm.token_context.trim()) {
    ElMessage.warning('请输入 Token JSON 内容')
    return
  }

  importing.value = true
  try {
    await importToken({
      token_context: importForm.token_context,
      name: importForm.name || null,
      max_usage_count: importForm.max_usage_count || null,
      task_type: importForm.task_type || 'google_sheet',
    })
    ElMessage.success('Token 新增成功')
    importForm.name = ''
    importForm.max_usage_count = 0
    importForm.token_context = ''
    await loadTokens()
  } catch {
    ElMessage.error('新增 Token 失败')
  } finally {
    importing.value = false
  }
}

async function openEditToken(id) {
  try {
    const res = await getToken(`${id}?include_context=1`)
    const token = res.token || {}
    tokenForm.id = token.id
    tokenForm.name = token.name || ''
    tokenForm.task_type = token.task_type || 'google_sheet'
    tokenForm.max_usage_count = token.max_usage_count || 0
    tokenForm.is_active = token.is_active ?? true
    tokenForm.token_context = token.token_context || ''
    tokenDialogVisible.value = true
  } catch {
    ElMessage.error('加载 Token 详情失败')
  }
}

async function handleSaveToken() {
  savingToken.value = true
  try {
    await updateToken(tokenForm.id, {
      name: tokenForm.name,
      task_type: tokenForm.task_type,
      max_usage_count: tokenForm.max_usage_count,
      is_active: tokenForm.is_active,
      token_context: tokenForm.token_context,
    })
    ElMessage.success('Token 更新成功')
    tokenDialogVisible.value = false
    await loadTokens()
  } catch {
    ElMessage.error('保存 Token 失败')
  } finally {
    savingToken.value = false
  }
}

async function handleDeleteToken() {
  await ElMessageBox.confirm('确定要删除这个 Token 吗？', '确认删除', { type: 'warning' })

  try {
    await deleteToken(tokenForm.id)
    ElMessage.success('Token 删除成功')
    tokenDialogVisible.value = false
    await loadTokens()
  } catch {
    ElMessage.error('删除 Token 失败')
  }
}

onMounted(loadAll)
</script>

<style scoped>
.card-header-row,
.dialog-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.config-metric {
  font-size: 22px;
  font-weight: 600;
  margin-top: 4px;
}

.config-actions {
  display: flex;
  justify-content: flex-end;
}

.dialog-footer__actions {
  display: flex;
  gap: 8px;
}

@media (max-width: 768px) {
  .dialog-footer {
    flex-direction: column;
    align-items: stretch;
  }

  .dialog-footer__actions {
    width: 100%;
  }

  .dialog-footer__actions :deep(.el-button) {
    flex: 1;
  }
}
</style>
