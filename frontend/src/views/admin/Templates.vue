<template>
  <div class="admin-templates">
    <PageToolbar eyebrow="管理中心" title="模板管理" description="管理任务配置模板">
      <template #actions>
        <el-button type="primary" @click="openCreateDialog">
          <el-icon><Plus /></el-icon> 创建模板
        </el-button>
      </template>
    </PageToolbar>

    <StatCardGrid
      :cards="[{ key: 'total', label: '模板总数', background: 'linear-gradient(135deg, #6366f1, #4f46e5)' }]"
      :data="statsData"
      :columns="{ xs: 12, sm: 6, md: 4 }"
      variant="gradient"
      class="mb-4"
    />

    <FilterToolbar
      :filters="FILTERS"
      v-model="filterValues"
      @search="loadTemplates"
      @clear="clearFilters"
      class="mb-3"
    />

    <el-table :data="templates" v-loading="loading" stripe style="width: 100%">
      <el-table-column prop="name" label="模板名称" min-width="180" show-overflow-tooltip />
      <el-table-column prop="type" label="类型" width="120" align="center">
        <template #default="{ row }">
          <el-tag size="small" effect="plain">{{ row.type }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="description" label="描述" min-width="200" show-overflow-tooltip />
      <el-table-column prop="created_at" label="创建时间" width="170">
        <template #default="{ row }"><span class="cell-time">{{ formatTime(row.created_at) }}</span></template>
      </el-table-column>
      <el-table-column prop="updated_at" label="更新时间" width="170">
        <template #default="{ row }"><span class="cell-time">{{ formatTime(row.updated_at) }}</span></template>
      </el-table-column>
      <el-table-column label="操作" width="160" fixed="right" align="center">
        <template #default="{ row }">
          <el-button type="primary" size="small" text @click.stop="openEditDialog(row)">编辑</el-button>
          <el-popconfirm title="确定删除此模板？" @confirm="handleDelete(row)">
            <template #reference>
              <el-button type="danger" size="small" text @click.stop>删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- Create/Edit Dialog -->
    <el-dialog
      v-model="dialogVisible"
      :title="isEdit ? '编辑模板' : '创建模板'"
      width="650px"
      destroy-on-close
    >
      <el-form :model="form" label-width="100px" :rules="rules" ref="formRef">
        <el-form-item label="模板名称" prop="name" required>
          <el-input v-model="form.name" placeholder="请输入模板名称" />
        </el-form-item>
        <el-form-item label="类型" prop="type" required>
          <el-select v-model="form.type" placeholder="选择类型" style="width: 100%">
            <el-option label="C3" value="c3" />
            <el-option label="C4" value="c4" />
            <el-option label="C5" value="c5" />
            <el-option label="回测训练" value="backtest_training" />
            <el-option label="多品种回测" value="backtest_multi" />
          </el-select>
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="2" placeholder="模板描述" />
        </el-form-item>
        <el-form-item label="配置 (JSON)" prop="config" required>
          <el-input
            v-model="form.config"
            type="textarea"
            :rows="12"
            placeholder="请输入 JSON 配置"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">
          {{ isEdit ? '保存' : '创建' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { getTemplates, createTemplate, updateTemplate, deleteTemplate } from '@/api/template'
import PageToolbar from '@/components/PageToolbar.vue'
import StatCardGrid from '@/components/StatCardGrid.vue'
import FilterToolbar from '@/components/FilterToolbar.vue'

const loading = ref(false)
const templates = ref([])
const statsData = ref({ total: 0 })

const filterValues = ref({ search: '', type: '' })
const FILTERS = [
  {
    key: 'type', type: 'select', label: '类型',
    options: [
      { label: '全部', value: '' },
      { label: 'C3', value: 'c3' },
      { label: 'C4', value: 'c4' },
      { label: 'C5', value: 'c5' },
      { label: '回测训练', value: 'backtest_training' },
      { label: '多品种回测', value: 'backtest_multi' },
    ],
  },
  { key: 'search', type: 'input', label: '搜索', placeholder: '模板名称' },
]

// Dialog
const dialogVisible = ref(false)
const isEdit = ref(false)
const formRef = ref(null)
const saving = ref(false)
const form = ref({ id: null, name: '', type: '', description: '', config: '' })
const rules = {
  name: [{ required: true, message: '请输入模板名称', trigger: 'blur' }],
  type: [{ required: true, message: '请选择类型', trigger: 'change' }],
  config: [{ required: true, message: '请输入配置', trigger: 'blur' }],
}

function formatTime(str) {
  if (!str) return '-'
  return new Date(str).toLocaleString('zh-CN')
}

function clearFilters() {
  filterValues.value = { search: '', type: '' }
  loadTemplates()
}

async function loadTemplates() {
  loading.value = true
  try {
    const params = { ...filterValues.value }
    Object.keys(params).forEach(k => { if (!params[k]) delete params[k] })
    const res = await getTemplates(params)
    const data = res?.data || res || {}
    templates.value = data.templates || data.items || data || []
    statsData.value = { total: data.total || templates.value.length }
  } catch {
    templates.value = []
  } finally {
    loading.value = false
  }
}

function openCreateDialog() {
  isEdit.value = false
  form.value = { id: null, name: '', type: '', description: '', config: '' }
  dialogVisible.value = true
}

function openEditDialog(row) {
  isEdit.value = true
  form.value = {
    id: row.id,
    name: row.name,
    type: row.type,
    description: row.description || '',
    config: typeof row.config === 'string' ? row.config : JSON.stringify(row.config || {}, null, 2),
  }
  dialogVisible.value = true
}

async function handleSave() {
  let configObj
  try {
    configObj = JSON.parse(form.value.config)
  } catch {
    ElMessage.warning('配置 JSON 格式无效')
    return
  }

  saving.value = true
  try {
    const payload = {
      name: form.value.name,
      type: form.value.type,
      description: form.value.description,
      config: configObj,
    }
    if (isEdit.value) {
      await updateTemplate(form.value.id, payload)
      ElMessage.success('模板已更新')
    } else {
      await createTemplate(payload)
      ElMessage.success('模板已创建')
    }
    dialogVisible.value = false
    loadTemplates()
  } catch {
    ElMessage.error(isEdit.value ? '更新失败' : '创建失败')
  } finally {
    saving.value = false
  }
}

async function handleDelete(row) {
  try {
    await deleteTemplate(row.id)
    ElMessage.success('已删除')
    loadTemplates()
  } catch {
    ElMessage.error('删除失败')
  }
}

onMounted(loadTemplates)
</script>

<style lang="scss" scoped>
.mb-4 { margin-bottom: 16px; }
.mb-3 { margin-bottom: 12px; }

.cell-time {
  font-size: var(--app-font-sm);
  color: var(--app-text-muted);
  white-space: nowrap;
}
</style>
